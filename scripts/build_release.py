#!/usr/bin/env python3
import gzip, hashlib, io, os, re, shutil, stat, tarfile, time, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _make_var(name, default):
    m = re.search(r"^" + name + r"\s*:?=\s*(\S+)", (ROOT / "Makefile").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else default

VERSION = _make_var("PKG_VERSION", "1.4.0")
RELEASE = _make_var("PKG_RELEASE", "1")
OUT = ROOT / "dist"

EXECUTABLES = {
    "etc/init.d/wan-latency", "usr/libexec/wan-latency-api",
    "usr/sbin/wan-latencyd", "usr/sbin/wan-latency-probe",
}

def tar_gz_bytes(roots=None, virtual=None, overrides=None):
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tf:
            for src_root, prefix in (roots or []):
                for path in sorted(src_root.rglob("*"), key=lambda p: p.as_posix()):
                    rel = prefix + path.relative_to(src_root).as_posix()
                    info = tarfile.TarInfo("./" + rel)
                    info.mtime = 0
                    if path.is_dir():
                        info.type = tarfile.DIRTYPE; info.mode = 0o755
                        tf.addfile(info)
                    else:
                        data = (overrides or {}).get(rel)
                        if data is None: data = path.read_bytes()
                        if isinstance(data, str): data = data.encode()
                        info.size = len(data)
                        info.mode = 0o755 if rel in EXECUTABLES else 0o644
                        tf.addfile(info, io.BytesIO(data))
            for name, (content, mode) in sorted((virtual or {}).items()):
                data = content.encode() if isinstance(content, str) else content
                info = tarfile.TarInfo("./" + name); info.size = len(data); info.mode = mode; info.mtime = 0
                tf.addfile(info, io.BytesIO(data))
    return raw.getvalue()

def _s8(b):
    return b - 256 if b >= 128 else b

def sfh(data):
    """SuperFastHash, compatible with luci-base po2lmo/sfh_hash (init=len)."""
    h = len(data) & 0xFFFFFFFF
    rem = len(data) & 3
    off = 0
    u16 = lambda o: data[o] | (data[o + 1] << 8)
    for _ in range(len(data) >> 2):
        h = (h + u16(off)) & 0xFFFFFFFF
        tmp = ((u16(off + 2) << 11) ^ h) & 0xFFFFFFFF
        h = ((h << 16) ^ tmp) & 0xFFFFFFFF
        off += 4
        h = (h + (h >> 11)) & 0xFFFFFFFF
    if rem == 3:
        h = (h + u16(off)) & 0xFFFFFFFF
        h ^= (h << 16) & 0xFFFFFFFF
        h ^= (_s8(data[off + 2]) << 18) & 0xFFFFFFFF
        h = (h + (h >> 11)) & 0xFFFFFFFF
    elif rem == 2:
        h = (h + u16(off)) & 0xFFFFFFFF
        h ^= (h << 11) & 0xFFFFFFFF
        h = (h + (h >> 17)) & 0xFFFFFFFF
    elif rem == 1:
        h = (h + _s8(data[off])) & 0xFFFFFFFF
        h ^= (h << 10) & 0xFFFFFFFF
        h = (h + (h >> 1)) & 0xFFFFFFFF
    h ^= (h << 3) & 0xFFFFFFFF; h = (h + (h >> 5)) & 0xFFFFFFFF
    h ^= (h << 4) & 0xFFFFFFFF; h = (h + (h >> 17)) & 0xFFFFFFFF
    h ^= (h << 25) & 0xFFFFFFFF; h = (h + (h >> 6)) & 0xFFFFFFFF
    return h

def _po_unquote(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] in '"\\':
            out.append(s[i + 1]); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)

def _parse_po(path):
    entries = []
    msgid, msgstr, cur = None, "", None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            if msgid is not None:
                entries.append((msgid, msgstr))
            msgid, msgstr, cur = "", "", "id"
            msgid = _po_unquote(line[line.index('"') + 1:line.rindex('"')])
        elif line.startswith("msgstr"):
            cur = "str"
            msgstr = _po_unquote(line[line.index('"') + 1:line.rindex('"')])
        elif line.startswith("msgid_plural"):
            cur = None
        elif line.startswith('"') and cur:
            s = _po_unquote(line[line.index('"') + 1:line.rindex('"')])
            if cur == "id": msgid += s
            else: msgstr += s
    if msgid is not None:
        entries.append((msgid, msgstr))
    return entries

def build_lmo(po_path):
    """Compile a .po file into LuCI LMO format (same layout as po2lmo)."""
    import struct
    entries, blob, offset = [], io.BytesIO(), 0
    def add(key_id, val_id, data):
        nonlocal offset
        entries.append((key_id, val_id, offset, len(data)))
        blob.write(data)
        blob.write(b"\0" * (-len(data) % 4))
        offset += len(data) + (-len(data) % 4)
    for msgid, msgstr in _parse_po(po_path):
        if not msgid:
            m = re.search(r"Plural-Forms: ([^\\]*)", msgstr)
            if m:
                add(0, 0, m.group(1).encode("utf-8"))
            continue
        if not msgstr:
            continue
        mid, mst = msgid.encode("utf-8"), msgstr.encode("utf-8")
        key_id = sfh(mid)
        if key_id != sfh(mst):
            add(key_id, 1, mst)
    out = io.BytesIO()
    out.write(blob.getvalue())
    idx_off = offset
    for key_id, val_id, off, length in sorted(entries):
        out.write(struct.pack(">IIII", key_id, val_id, off, length))
    out.write(struct.pack(">I", idx_off))
    return out.getvalue()

def ar_member(name, data):
    stamp = "0"; header = f"{name + '/':<16}{stamp:<12}{'0':<6}{'0':<6}{'100644':<8}{len(data):<10}`\n".encode()
    return header + data + (b"\n" if len(data) % 2 else b"")

def outer_ipk(data_tar, control_tar):
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tf:
            for name, data in (("debian-binary", b"2.0\n"), ("data.tar.gz", data_tar), ("control.tar.gz", control_tar)):
                info = tarfile.TarInfo("./" + name); info.size = len(data); info.mode = 0o644; info.mtime = 0
                tf.addfile(info, io.BytesIO(data))
    return raw.getvalue()

def versioned_overrides():
    """Rewrite the iframe ?v= cache-buster to this release's version."""
    view = ROOT / "htdocs/luci-static/resources/view/status/wan_latency.js"
    src = view.read_text(encoding="utf-8")
    out, n = re.subn(r"index\.html\?v=[A-Za-z0-9._-]*", f"index.html?v={VERSION}-{RELEASE}", src)
    if n != 1:
        raise SystemExit("expected exactly one 'index.html?v=' marker in " + str(view))
    return {"www/luci-static/resources/view/status/wan_latency.js": out}

def build_ipk(name, data_roots, depends, description, conffiles="", postinst="", prerm="", data_virtual=None, data_overrides=None):
    filename = f"{name}_{VERSION}-{RELEASE}_all.ipk"
    control = f"Package: {name}\nVersion: {VERSION}-{RELEASE}\nArchitecture: all\nMaintainer: xiaokeikei\nSection: luci\nPriority: optional\nDepends: {depends}\nDescription: {description}\n"
    controls = {"control": (control, 0o644)}
    if conffiles: controls["conffiles"] = (conffiles, 0o644)
    if postinst: controls["postinst"] = (postinst, 0o755)
    if prerm: controls["prerm"] = (prerm, 0o755)
    blob = outer_ipk(tar_gz_bytes(roots=data_roots, virtual=data_virtual, overrides=data_overrides), tar_gz_bytes(virtual=controls))
    (OUT / filename).write_bytes(blob)
    return filename

def build_run(main_ipk):
    payload = tar_gz_bytes(virtual={main_ipk: ((OUT / main_ipk).read_bytes(), 0o644)})
    header = f'''#!/bin/sh
set -eu
fail() {{ echo "Error: $*" >&2; exit 1; }}
[ "$(id -u)" = "0" ] || fail "run this installer as root"
[ -f /etc/openwrt_release ] || fail "this installer is only for OpenWrt-compatible systems"
missing=""
for p in luci-base lua luci-lib-nixio cgi-io rpcd-mod-file curl ip-full; do
  opkg status "$p" 2>/dev/null | grep -q '^Status:.* installed' || missing="$missing $p"
done
[ -z "$missing" ] || fail "missing packages:$missing (run: opkg update && opkg install$missing)"
work="$(mktemp -d /tmp/wan-latency-install.XXXXXX)"
trap 'rm -rf "$work"' EXIT INT TERM
line="$(awk '/^__PAYLOAD_BELOW__$/ {{ print NR + 1; exit }}' "$0")"
tail -n "+$line" "$0" | gzip -dc | tar -xf - -C "$work"
opkg install "$work/{main_ipk}"
echo "luci-app-wan-latency installation completed"
exit 0
__PAYLOAD_BELOW__
'''.encode()
    name = f"luci-app-wan-latency-{VERSION}-{RELEASE}.run"
    (OUT / name).write_bytes(header + payload)
    return name

def source_zip():
    name = f"luci-app-wan-latency-{VERSION}-{RELEASE}-source.zip"
    prefix = f"luci-app-wan-latency-{VERSION}/"
    with zipfile.ZipFile(OUT / name, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(ROOT.rglob("*"), key=lambda x: x.as_posix()):
            rel = p.relative_to(ROOT)
            if not p.is_file() or ".git" in rel.parts or "__pycache__" in rel.parts or p.suffix == ".pyc" or (rel.parts and rel.parts[0] in {"dist", "work"}): continue
            z.write(p, prefix + rel.as_posix())
    return name

def main():
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir()
    lmo = build_lmo(ROOT / "po/zh_Hans/wan-latency.po")
    main_ipk = build_ipk(
        "luci-app-wan-latency",
        [(ROOT / "root", ""), (ROOT / "htdocs", "www/")],
        "luci-base, lua, luci-lib-nixio, cgi-io, rpcd-mod-file, curl, ip-full",
        "WAN latency monitor for LuCI",
        "/etc/config/wan-latency\n",
        "#!/bin/sh\n[ -n \"$IPKG_INSTROOT\" ] || { /etc/init.d/wan-latency enable; /etc/init.d/wan-latency restart; rm -f /www/cgi-bin/wan-latency /tmp/luci-indexcache.* 2>/dev/null; rm -rf /tmp/luci-modulecache/; /etc/init.d/rpcd reload 2>/dev/null; /etc/init.d/uhttpd reload 2>/dev/null; }\nexit 0\n",
        "#!/bin/sh\n[ -n \"$IPKG_INSTROOT\" ] || /etc/init.d/wan-latency stop\nexit 0\n",
        {"usr/lib/lua/luci/i18n/wan-latency.zh-cn.lmo": (lmo, 0o644)},
        versioned_overrides())
    names = [main_ipk, build_run(main_ipk), source_zip()]
    sums = []
    for name in names:
        sums.append(hashlib.sha256((OUT / name).read_bytes()).hexdigest() + "  " + name)
    (OUT / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    shutil.copy2(ROOT / "RELEASE_NOTES.md", OUT / "RELEASE_NOTES.md")
    print("\n".join(str(OUT / n) for n in names + ["SHA256SUMS", "RELEASE_NOTES.md"]))

if __name__ == "__main__": main()
