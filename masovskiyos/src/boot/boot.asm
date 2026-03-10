; ==================================================================
; OpenAssemblyToolBox -- The OpenATB bootloader
; Copyright (C) 2026 Roman Mas0vsk1yy
;
; Loads the kernel (KERNEL.BIN) for execution.
; Uses OpenASM file system.
; ==================================================================

[org 0x7C00]
[bits 16]

KERNEL_SEGMENT equ 0x1000
KERNEL_OFFSET  equ 0x0000
KERNEL_SECTORS equ 127

start:
    mov [BOOT_DRIVE], dl
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti

    mov ax, 0x0003
    int 0x10

    mov si, splash_top
    call print_string
    mov si, splash_mid
    call print_string
    mov si, splash_bot
    call print_string
    ; OATB_PATCH_BOOT_CODE

    mov ax, KERNEL_SEGMENT
    mov es, ax
    mov bx, KERNEL_OFFSET
    mov dh, KERNEL_SECTORS
    mov dl, [BOOT_DRIVE]
    call disk_load
    mov dl, [BOOT_DRIVE]
    jmp KERNEL_SEGMENT:KERNEL_OFFSET

hang:
    jmp hang

disk_load:
    pusha
    mov di, bx
    mov si, 1
    mov [KERNEL_LEFT], dh
.load_next:
    cmp byte [KERNEL_LEFT], 0
    je .done

    mov ax, si
    xor dx, dx
    mov bp, 36
    div bp
    mov ch, al

    mov ax, dx
    xor dx, dx
    mov bp, 18
    div bp
    mov dh, al
    mov cl, dl
    inc cl

    mov bx, di
    mov dl, [BOOT_DRIVE]
    mov ah, 0x02
    mov al, 1
    int 0x13
    jc disk_error

    inc si
    add di, 512
    dec byte [KERNEL_LEFT]
    jmp .load_next
.done:
    popa
    ret

disk_error:
    mov si, disk_error_msg
    call print_string
    jmp hang

print_string:
    mov ah, 0x0E
.loop:
    lodsb
    cmp al, 0
    je .done
    int 0x10
    jmp .loop
.done:
    ret

BOOT_DRIVE db 0
KERNEL_LEFT db 0

splash_top db 13,10, "========================================", 13,10, 0
splash_mid db "      masovskiyos Bootloader      ", 13,10, 0
splash_bot db "========================================", 13,10, 0
disk_error_msg db "Disk read error. System halted.", 13,10, 0
; OATB_PATCH_BOOT_DATA

times 510-($-$$) db 0
dw 0xAA55
