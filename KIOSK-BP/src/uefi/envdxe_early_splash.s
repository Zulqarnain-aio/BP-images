// EnvDxe additions for v5: show the splash as soon as DisplayDxe is up.
// External addresses (EnvDxe image offsets) come in via --defsym.
	.text
	.globl reg_hook, wrapper

// Replaces "ldp x29, x30, [sp, #16]" at 0x2c08, the tail of the function
// that registers the "display set mode" event (entry: bl 0x2b94).
// Also have wrapper() called when DisplayDxe installs EFI_DISPLAY_UTILS.
reg_hook:
	stp x29, x30, [sp, #-48]!
	mov x29, sp
	adrp x8, GBS_PTR
	ldr x8, [x8, :lo12:GBS_PTR]
	ldr x9, [x8, #80]             // gBS->CreateEvent
	mov w0, #0x200                // EVT_NOTIFY_SIGNAL
	mov x1, #8                    // TPL_CALLBACK
	adr x2, wrapper
	mov x3, xzr
	add x4, sp, #16
	blr x9
	cbnz x0, 1f
	adrp x8, GBS_PTR
	ldr x8, [x8, :lo12:GBS_PTR]
	ldr x9, [x8, #168]            // gBS->RegisterProtocolNotify
	adrp x0, DU_GUID
	add x0, x0, :lo12:DU_GUID
	ldr x1, [sp, #16]
	add x2, sp, #24
	blr x9
1:	ldp x29, x30, [sp], #48
	ldp x29, x30, [sp, #16]       // displaced instruction
	b RET_2C0C

// Notify function for both events. First run (DisplayUtils installed, ~1.8 s):
// GOP SetMode(0) so the later GraphicsConsole SetMode is a no-op, then the
// original callback (logo, LT9211D, backlight). Later runs only redraw the
// logo, which GraphicsConsole clears when it connects.
wrapper:
	stp x29, x30, [sp, #-128]!
	mov x29, sp
	str x19, [sp, #16]
	adrp x19, FLAG
	ldrb w8, [x19, :lo12:FLAG]
	cbnz w8, 5f
	adrp x8, GBS_PTR
	ldr x8, [x8, :lo12:GBS_PTR]
	ldr x9, [x8, #320]            // gBS->LocateProtocol(DisplayUtils)
	adrp x0, DU_GUID
	add x0, x0, :lo12:DU_GUID
	mov x1, xzr
	add x2, sp, #24
	blr x9
	cbnz x0, 9f                   // display not up yet: try again next time
	mov w8, #1
	strb w8, [x19, :lo12:FLAG]
	adrp x8, GBS_PTR
	ldr x8, [x8, :lo12:GBS_PTR]
	ldr x9, [x8, #320]            // gBS->LocateProtocol(GOP)
	adr x0, gop_guid
	mov x1, xzr
	add x2, sp, #24
	blr x9
	cbnz x0, 2f
	ldr x0, [sp, #24]
	ldr x9, [x0, #8]              // GOP->SetMode(This, 0)
	mov w1, wzr
	blr x9
2:	ldr x19, [sp, #16]
	ldp x29, x30, [sp], #128
	b CALLBACK                    // original SplashScreenRenderCallback

5:	adrp x8, GBS_PTR
	ldr x8, [x8, :lo12:GBS_PTR]
	ldr x9, [x8, #320]
	adrp x0, DU_GUID
	add x0, x0, :lo12:DU_GUID
	mov x1, xzr
	add x2, sp, #24
	blr x9
	cbnz x0, 9f
	stp xzr, xzr, [sp, #32]       // EFI_DISPLAY_UTILS_RENDERLOGO_CONFIG
	stp xzr, xzr, [sp, #48]
	stp xzr, xzr, [sp, #64]
	stp xzr, xzr, [sp, #80]
	mov w8, #1
	str w8, [sp, #36]             // uFlags = 1, as the original callback
	ldr x8, [sp, #24]
	ldr x9, [x8, #24]             // DisplayUtilsRenderLogo
	add x0, sp, #32
	blr x9
9:	ldr x19, [sp, #16]
	ldp x29, x30, [sp], #128
	ret

	.balign 8
gop_guid:	// 9042a9de-23dc-4a38-96fb-7aded080516a
	.long 0x9042a9de
	.short 0x23dc, 0x4a38
	.byte 0x96, 0xfb, 0x7a, 0xde, 0xd0, 0x80, 0x51, 0x6a
