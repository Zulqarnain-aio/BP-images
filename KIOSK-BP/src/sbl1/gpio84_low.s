// SBL1 stub (v2, v4, v5): drive GPIO84 (Disp_EN, backlight enable) low.
// Called in place of the SBL1 log function; tail-calls it.
// TLMM GPIO84: cfg 0x954000, in/out 0x954004 (TLMM 0x400000 + SOUTH 0x500000 + 84 * 0x1000).
	.text
	movz w9, #0x4000
	movk w9, #0x95, lsl #16
	str wzr, [x9, #4]            // out = 0 before enabling the driver
	movz w10, #0x3c1             // OE, 16 mA, pull-down, func 0 (GPIO)
	str w10, [x9]
	str wzr, [x9, #4]
	dsb sy
	b SBL1_LOG
