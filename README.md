# luci-app-wan-latency

一个适用于 OpenWrt / iStoreOS 的公网延迟监控插件。它持续从 WAN 接口探测多个目标，将数据保存在路由器本地，并在 LuCI「状态 → 公网延迟」中展示实时状态和历史曲线。

## 功能

- 同时监控最多 12 个 IPv4 地址或域名
- ICMP 不可用时依次尝试 HTTPS、HTTP 和 DNS 探测
- 支持 2 秒至 5 分钟的采样间隔
- 支持 15 分钟至 1 年以及自定义时间范围
- 原始数据和 1 分钟汇总数据使用紧凑二进制格式保存
- 默认保留 366 天数据
- 自带阿里云、腾讯云和 Steam 三个预设目标

## 依赖

- `luci-base`
- `lua`
- `luci-lib-nixio`
- `curl`
- `ip-full`

## 编译

将本目录复制到 OpenWrt SDK 或源码树的 `package/luci-app-wan-latency`：

```sh
make menuconfig
# LuCI -> Applications -> luci-app-wan-latency
make package/luci-app-wan-latency/compile V=s
```

生成的 `.ipk` 或 `.apk` 可在对应架构、对应 OpenWrt 版本的设备上安装。

## 数据与配置

- UCI 配置：`/etc/config/wan-latency`
- 目标列表：`/etc/wan-latency/targets.conf`
- 当前采样间隔：`/etc/wan-latency/interval`
- 历史数据：`/overlay/wan-latency/data/`
- 临时实时状态：`/tmp/wan-latency-latest.json`

历史数据、实时状态和设备上的自定义目标均未包含在本仓库中。

## 发布前注意

当前 Web API 位于 `/www/cgi-bin/wan-latency`，并包含增删目标、调整顺序和修改采样间隔等写操作。公开发布前建议将 API 改为经过 LuCI 会话与 ACL 鉴权的 rpcd/ubus 接口，避免同一网络中的未授权访问与跨站请求。

## 来源与许可

本仓库由一台正在运行的 iStoreOS 设备上的自用插件整理而成。发布者需要在公开发布前确认全部代码的著作权归属，并选择合适的开源许可证；当前软件包元数据使用 `UNLICENSED`，仓库不授予再分发许可。
