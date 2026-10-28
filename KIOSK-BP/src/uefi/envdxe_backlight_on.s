// EnvDxe (v4, v5): turn the backlight on 250 ms after the LT9211D is running.
// Replaces the 1 ms MicroSecondDelay call in the Ctrl+C poll loop that follows
// the LT9211D init in Quectel's SplashScreenRenderCallback; w20 counts the
// iterations (ms since "LT9211D init complete"). Panel T3 >= 200 ms.
	.text
	cmp w20, #250
	b.ne 9f
	stp x29, x30, [sp, #-32]!
	mov x29, sp
	str x0, [sp, #16]
	adrp x8, TLMM_PTR
	ldr x8, [x8, :lo12:TLMM_PTR]  // EFI_TLMM_PROTOCOL *
	cbz x8, 8f
	ldr x9, [x8, #32]             // EFI_TLMM_PROTOCOL.GpioOut
	movz w0, #0x4540
	movk w0, #0x200e, lsl #16     // EFI_GPIO_CFG(84, 0, OUT, NO_PULL, 16MA), as DisplayDxe uses
	orr w1, wzr, #1               // GPIO_HIGH_VALUE: backlight on
	blr x9
8:	ldr x0, [sp, #16]
	ldp x29, x30, [sp], #32
9:	b ENV_DELAY
