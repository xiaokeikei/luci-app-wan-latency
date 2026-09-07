'use strict';
'require view';

return view.extend({
	render: function () {
		var frame = E('iframe', {
			src: '/wan-latency/index.html?v=20260907filter',
			style: 'width:100%;height:calc(100vh - 120px);border:0;border-radius:12px;background:transparent'
		});
		return E('div', { style: 'margin:-8px' }, [frame]);
	},
	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});