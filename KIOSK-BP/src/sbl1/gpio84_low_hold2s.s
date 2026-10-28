// SBL1 stub (v3, diagnostic only): drive GPIO84 low, then hold SBL1 for 2 s
// so the effect on the backlight is unmistakable. Never ship this.
	.text
	movz w9, #0x4000
	movk w9, #0x95, lsl #16      // TLMM GPIO84 cfg 0x954000
	str wzr, [x9, #4]            // io: out low
	movz w10, #0x3c1             // OE | 16 mA | pull-down, func 0
	str w10, [x9]
	str wzr, [x9, #4]
	dsb sy
	mrs x10, cntfrq_el0
	lsl x10, x10, #1             // 2 s of ticks
	isb
	mrs x11, cntpct_el0
	add x11, x11, x10
	movz w12, #0x800, lsl #16    // iteration cap in case the counter is not running
1:	isb
	mrs x10, cntpct_el0
	cmp x10, x11
	b.hs 2f
	subs w12, w12, #1
	b.ne 1b
2:	b SBL1_LOG
