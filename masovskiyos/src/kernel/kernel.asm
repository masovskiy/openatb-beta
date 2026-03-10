; ==================================================================
; OpenAssemblyToolBox -- OpenATB kernel
; Copyright (C) 2026 Roman Mas0vsk1yy
;
; Core shell runtime, Open Assembly FS, and OATB DevKit support.
; ==================================================================

[org 0x0000]
[bits 16]

MAX_INPUT equ 255
USER_MAX  equ 32
PASS_MAX equ 32
REGION_MAX equ 23
FS_NAME_MAX equ 31
FS_TEXT_MAX equ 3072
NANO_MAX_LINES equ 1000
FS_STORE_LBA equ 256
FS_STORE_SECTORS equ 64
FS_STORE_SEG equ 0x2000
FS_STORE_BUFFER equ 0x0000

COLOR_DEFAULT equ 0x07
COLOR_INFO    equ 0x0B
COLOR_WARN    equ 0x0E
COLOR_ERROR   equ 0x0C
COLOR_PROMPT  equ 0x0A
COLOR_ASCII   equ 0x0D
COLOR_FRAME   equ 0x09
COLOR_ACCENT  equ 0x03
COLOR_TITLE   equ 0x0F
COLOR_BANNER_1 equ 0x09
COLOR_BANNER_2 equ 0x0B
COLOR_BANNER_3 equ 0x0D
COLOR_BANNER_4 equ 0x0E
COLOR_BANNER_5 equ 0x0A
COLOR_BANNER_6 equ 0x03

start:
    cli
    mov ax, cs
    mov ds, ax
    mov es, ax
    mov [boot_drive], dl
    mov ax, 0x7000
    mov ss, ax
    mov sp, 0xFFF0
    sti
    call clear_screen
    call show_banner
    mov bl, COLOR_TITLE
    mov si, boot_msg
    call print_color_string
    call init_boot_ticks
    call init_openasm_fs
    call init_runtime_strings
    call fs_store_load
    call sanitize_runtime_state
    call first_boot_setup
    call show_boot_notice
    ; OATB_PATCH_KERNEL_BOOT

shell_loop:
    call show_prompt
    mov di, input_buffer
    call read_line
    mov si, input_buffer
    call dispatch_command
    jmp shell_loop

dispatch_command:
    cmp byte [si], 0
    je .done

    mov di, cmd_help
    call strcmp
    cmp ax, 1
    je .help

    mov di, cmd_about
    call strcmp
    cmp ax, 1
    je .about

    mov di, cmd_clear
    call strcmp
    cmp ax, 1
    je .clear

    mov di, cmd_cls
    call strcmp
    cmp ax, 1
    je .clear

    mov di, cmd_banner
    call strcmd
    cmp ax, 1
    je .banner

    mov di, cmd_patches
    call strcmd
    cmp ax, 1
    je .patches

    mov di, cmd_sys
    call strcmd
    cmp ax, 1
    je .sys

    mov di, cmd_uptime
    call strcmd
    cmp ax, 1
    je .uptime

    mov di, cmd_time
    call strcmd
    cmp ax, 1
    je .time

    mov di, cmd_date
    call strcmd
    cmp ax, 1
    je .date

    mov di, cmd_version
    call strcmd
    cmp ax, 1
    je .version

    mov di, cmd_fetch
    call strcmp
    cmp ax, 1
    je .fetch

    mov di, cmd_exit
    call strcmp
    cmp ax, 1
    je .exit

    mov di, cmd_echo
    call strcmd
    cmp ax, 1
    je .echo

    mov di, cmd_setname
    call strcmd
    cmp ax, 1
    je .setname

    mov di, cmd_region
    call strcmd
    cmp ax, 1
    je .region

    mov di, cmd_passwd
    call strcmd
    cmp ax, 1
    je .passwd

    mov di, cmd_cd
    call strcmd
    cmp ax, 1
    je .cd

    mov di, cmd_reboot
    call strcmp
    cmp ax, 1
    je .reboot

    mov di, cmd_ls
    call strcmp
    cmp ax, 1
    je .fsls

    mov di, cmd_fsls
    call strcmp
    cmp ax, 1
    je .fsls

    mov di, cmd_fsinfo
    call strcmp
    cmp ax, 1
    je .fsinfo

    mov di, cmd_fswrite
    call strcmd
    cmp ax, 1
    je .fswrite

    mov di, cmd_write
    call strcmd
    cmp ax, 1
    je .fswrite

    mov di, cmd_append
    call strcmd
    cmp ax, 1
    je .append

    mov di, cmd_rm
    call strcmd
    cmp ax, 1
    je .rmfile

    mov di, cmd_touch
    call strcmd
    cmp ax, 1
    je .touch

    mov di, cmd_mk
    call strcmd
    cmp ax, 1
    je .touch

    mov di, cmd_mkdir
    call strcmd
    cmp ax, 1
    je .mkdir

    mov di, cmd_rmdir
    call strcmd
    cmp ax, 1
    je .rmdir

    mov di, cmd_cat
    call strcmd
    cmp ax, 1
    je .cat

    mov di, cmd_nano
    call strcmd
    cmp ax, 1
    je .nano

    ; OATB_PATCH_KERNEL_COMMANDS
; OATB_PATCH_APPLIED_customize_1
    mov di, cmd_atbman
    call strcmd
    cmp ax, 1
    jne .patch_customize_after_atbman
    add si, 6
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_usage
    mov di, arg_dash_h
    call strcmp
    cmp ax, 1
    je .patch_customize_usage
    mov di, arg_dash_dash_help
    call strcmp
    cmp ax, 1
    je .patch_customize_usage
    mov di, arg_dash_l
    call strcmp
    cmp ax, 1
    je .patch_customize_list
    mov di, arg_dash_dash_list
    call strcmp
    cmp ax, 1
    je .patch_customize_list
    mov di, arg_dash_e
    call strcmd
    cmp ax, 1
    je .patch_customize_exec_short
    mov di, arg_dash_dash_exec
    call strcmd
    cmp ax, 1
    je .patch_customize_exec_long
    mov di, arg_dash_i
    call strcmd
    cmp ax, 1
    je .patch_customize_install_short
    mov di, arg_dash_dash_install
    call strcmd
    cmp ax, 1
    je .patch_customize_install_long
    mov di, arg_dash_u
    call strcmd
    cmp ax, 1
    je .patch_customize_uninstall_short
    mov di, arg_dash_dash_uninstall
    call strcmd
    cmp ax, 1
    je .patch_customize_uninstall_long
    jmp .patch_customize_usage
.patch_customize_exec_short:
    add si, 2
    jmp .patch_customize_exec_tail
.patch_customize_exec_long:
    add si, 6
.patch_customize_exec_tail:
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_usage
    mov di, atb_arg_name
    mov cx, 32
    call .patch_customize_copy_token
    call .patch_customize_exec_program
    ret
.patch_customize_install_short:
    add si, 2
    jmp .patch_customize_install_tail
.patch_customize_install_long:
    add si, 9
.patch_customize_install_tail:
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_usage
    mov di, atb_arg_name
    mov cx, 32
    call .patch_customize_copy_token
    mov si, runtime_atbdevkit
    mov di, atb_arg_runtime
    call copy_string
    call skip_spaces
    cmp byte [si], 0
    jne .patch_customize_install_with_source
    mov si, atb_source_default
    mov di, atb_arg_source
    call copy_string
    jmp .patch_customize_install_apply
.patch_customize_install_with_source:
    mov di, atb_arg_source
    mov cx, 64
    call .patch_customize_copy_token
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_install_apply
    mov di, atb_arg_runtime
    mov cx, 15
    call .patch_customize_copy_token
.patch_customize_install_apply:
    call .patch_customize_install_program
    ret
.patch_customize_uninstall_short:
    add si, 2
    jmp .patch_customize_uninstall_tail
.patch_customize_uninstall_long:
    add si, 11
.patch_customize_uninstall_tail:
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_usage
    mov di, atb_arg_name
    mov cx, 32
    call .patch_customize_copy_token
    call .patch_customize_uninstall_program
    ret
.patch_customize_list:
    call .patch_customize_list_programs
    ret
.patch_customize_usage:
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_usage
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_example_exec
    call print_color_string
    mov si, msg_atbman_example_install
    call print_color_string
    mov si, msg_atbman_example_uninstall
    call print_color_string
    ret
.patch_customize_after_atbman:
    jmp .patch_customize_dispatch_continue
.patch_customize_copy_token:
    push ax
    push dx
    mov dx, cx
    cmp dx, 0
    jne .patch_customize_copy_token_loop
    mov byte [di], 0
    jmp .patch_customize_copy_token_done
.patch_customize_copy_token_loop:
    mov al, [si]
    cmp al, 0
    je .patch_customize_copy_token_end
    cmp al, ' '
    je .patch_customize_copy_token_end
    cmp dx, 0
    je .patch_customize_copy_token_skip_store
    mov [di], al
    inc di
    dec dx
.patch_customize_copy_token_skip_store:
    inc si
    jmp .patch_customize_copy_token_loop
.patch_customize_copy_token_end:
    mov byte [di], 0
.patch_customize_copy_token_done:
    pop dx
    pop ax
    ret
.patch_customize_exec_program:
    mov si, atb_arg_name
    mov di, fs_name_cscript
    call strcmp
    cmp ax, 1
    jne .patch_customize_exec_check_slot1
    cmp byte [cscript_enabled], 1
    jne .patch_customize_exec_check_slot1
.patch_customize_apply_script:
    call .patch_customize_apply_cscript_profile
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_cscript
    call print_color_string
    call .patch_customize_openact
    ret
.patch_customize_exec_check_slot1:
    mov di, atb_pkg1_name
    call strcmp
    cmp ax, 1
    je .patch_customize_exec_slot1
    mov di, atb_pkg2_name
    call strcmp
    cmp ax, 1
    je .patch_customize_exec_slot2
    mov di, atb_pkg3_name
    call strcmp
    cmp ax, 1
    je .patch_customize_exec_slot3
    mov si, atb_arg_name
    call fs_user_find_by_name
    cmp ax, 1
    je .patch_customize_exec_local
    mov bl, COLOR_ERROR
    mov si, msg_atbman_exec_missing_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_arg_name
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    call fs_store_save
    ret
.patch_customize_exec_slot1:
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg1_name
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_from
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg1_source
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_runtime_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg1_runtime
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov si, atb_pkg1_runtime
    mov di, runtime_python
    call strcmp
    cmp ax, 1
    jne .patch_customize_exec_slot1_check_c
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_runtime_python_hint
    call print_color_string
    jmp .patch_customize_exec_slot1_hint_done
.patch_customize_exec_slot1_check_c:
    mov si, atb_pkg1_runtime
    mov di, runtime_c
    call strcmp
    cmp ax, 1
    jne .patch_customize_exec_slot1_hint_done
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_runtime_c_hint
    call print_color_string
.patch_customize_exec_slot1_hint_done:
    mov si, atb_pkg1_name
    call fs_user_find_by_name
    cmp ax, 1
    jne .patch_customize_exec_slot1_done
    mov si, di
    call .patch_customize_exec_source
.patch_customize_exec_slot1_done:
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_done
    call print_color_string
    ret
.patch_customize_exec_slot2:
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg2_name
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_from
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg2_source
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_runtime_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg2_runtime
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov si, atb_pkg2_runtime
    mov di, runtime_python
    call strcmp
    cmp ax, 1
    jne .patch_customize_exec_slot2_check_c
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_runtime_python_hint
    call print_color_string
    jmp .patch_customize_exec_slot2_hint_done
.patch_customize_exec_slot2_check_c:
    mov si, atb_pkg2_runtime
    mov di, runtime_c
    call strcmp
    cmp ax, 1
    jne .patch_customize_exec_slot2_hint_done
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_runtime_c_hint
    call print_color_string
.patch_customize_exec_slot2_hint_done:
    mov si, atb_pkg2_name
    call fs_user_find_by_name
    cmp ax, 1
    jne .patch_customize_exec_slot2_done
    mov si, di
    call .patch_customize_exec_source
.patch_customize_exec_slot2_done:
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_done
    call print_color_string
    ret
.patch_customize_exec_slot3:
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg3_name
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_from
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg3_source
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_runtime_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg3_runtime
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov si, atb_pkg3_runtime
    mov di, runtime_python
    call strcmp
    cmp ax, 1
    jne .patch_customize_exec_slot3_check_c
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_runtime_python_hint
    call print_color_string
    jmp .patch_customize_exec_slot3_hint_done
.patch_customize_exec_slot3_check_c:
    mov si, atb_pkg3_runtime
    mov di, runtime_c
    call strcmp
    cmp ax, 1
    jne .patch_customize_exec_slot3_hint_done
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_runtime_c_hint
    call print_color_string
.patch_customize_exec_slot3_hint_done:
    mov si, atb_pkg3_name
    call fs_user_find_by_name
    cmp ax, 1
    jne .patch_customize_exec_slot3_done
    mov si, di
    call .patch_customize_exec_source
.patch_customize_exec_slot3_done:
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_done
    call print_color_string
    ret
.patch_customize_exec_local:
    push di
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_arg_name
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_from
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_source_local
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_runtime_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, runtime_atbdevkit
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    pop si
    call .patch_customize_exec_source
    mov bl, [cfg_color_info]
    mov si, msg_atbman_exec_done
    call print_color_string
    ret
.patch_customize_exec_source:
    push ax
    push bx
    push cx
    push dx
    push di
    mov byte [atb_var_name], 0
    mov byte [atb_var_value], 0
    mov byte [atb_if_pending], 0
    mov byte [atb_if_result], 0
    mov word [atb_int_a], 0
    mov word [atb_int_b], 0
    mov word [atb_int_user_choice], 0
.patch_customize_exec_line:
    cmp byte [si], 0
    je .patch_customize_exec_source_done
    mov di, atb_line_buf
    mov cx, FS_TEXT_MAX
    mov byte [atb_quote_state], 0
.patch_customize_exec_copy_line:
    mov al, [si]
    cmp al, 0
    je .patch_customize_exec_line_end
    cmp al, 13
    je .patch_customize_exec_line_cr
    cmp al, 10
    je .patch_customize_exec_line_lf
    cmp al, '"'
    jne .patch_customize_exec_copy_line_check_sc
    xor byte [atb_quote_state], 1
    jmp .patch_customize_exec_copy_line_store
.patch_customize_exec_copy_line_check_sc:
    cmp al, ';'
    je .patch_customize_exec_line_sc
.patch_customize_exec_copy_line_store:
    cmp cx, 0
    je .patch_customize_exec_copy_skip_store
    mov [di], al
    inc di
    dec cx
.patch_customize_exec_copy_skip_store:
    inc si
    jmp .patch_customize_exec_copy_line
.patch_customize_exec_line_cr:
    inc si
    cmp byte [si], 10
    jne .patch_customize_exec_line_end
    inc si
    jmp .patch_customize_exec_line_end
.patch_customize_exec_line_lf:
    inc si
    jmp .patch_customize_exec_line_end
.patch_customize_exec_line_sc:
    cmp byte [atb_quote_state], 0
    jne .patch_customize_exec_copy_line_store
    inc si
.patch_customize_exec_line_end:
    mov byte [di], 0
    mov [atb_exec_src_ptr], si
    mov si, atb_line_buf
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_exec_continue
    cmp byte [si], '<'
    je .patch_customize_exec_continue
    mov di, atb_devkit_cmd_func
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_continue
    mov di, atb_devkit_cmd_else
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_else
    mov byte [atb_if_pending], 0
    mov di, atb_devkit_cmd_if
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_if
    mov di, atb_devkit_cmd_output3
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_output3
    mov di, atb_devkit_cmd_output1
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_output1
    mov di, atb_devkit_cmd_output2
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_output2
    mov di, atb_devkit_cmd_run1
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_run1
    mov di, atb_devkit_cmd_run2
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_run2
    mov di, atb_devkit_cmd_clear
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_clear
    mov di, atb_devkit_cmd_menu_title
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_menu_title
    mov di, atb_devkit_cmd_menu_item
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_menu_item
    mov di, atb_devkit_cmd_menu_input
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_menu_input
    mov di, atb_devkit_cmd_var
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_var
    mov di, atb_devkit_cmd_write
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_write
    mov di, atb_devkit_cmd_append
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_append
    mov di, atb_devkit_cmd_read
    call strprefix
    cmp ax, 1
    je .patch_customize_exec_read
    jmp .patch_customize_exec_continue
.patch_customize_exec_output1:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_output2:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_output3:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_run1:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_run2:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_clear:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_menu_title:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_menu_item:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_menu_input:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_else:
    add si, 4
    call skip_spaces
    cmp byte [atb_if_pending], 1
    jne .patch_customize_exec_continue
    cmp byte [atb_if_result], 1
    je .patch_customize_exec_else_done
    call .patch_customize_find_arrow
    cmp ax, 1
    jne .patch_customize_exec_else_done
    call skip_spaces
    call .patch_customize_exec_inline_stmt
.patch_customize_exec_else_done:
    mov byte [atb_if_pending], 0
    mov byte [atb_if_result], 0
    jmp .patch_customize_exec_continue
.patch_customize_exec_if:
    mov byte [atb_if_pending], 1
    mov byte [atb_if_result], 0
    add si, 2
    call skip_spaces
    mov di, atb_if_left
    mov cx, 32
    call copy_token_limited
    call skip_spaces
    cmp byte [si], '='
    jne .patch_customize_exec_continue
    inc si
    cmp byte [si], '='
    jne .patch_customize_exec_continue
    inc si
    call skip_spaces
    call .patch_customize_parse_u16
    mov [atb_if_rhs], ax
    mov si, atb_if_left
    call .patch_customize_get_named_int
    cmp dx, 1
    jne .patch_customize_exec_continue
    cmp ax, [atb_if_rhs]
    jne .patch_customize_exec_continue
    mov byte [atb_if_result], 1
    call .patch_customize_find_arrow
    cmp ax, 1
    jne .patch_customize_exec_continue
    call skip_spaces
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_inline_stmt:
    push bx
    push cx
    push di
    mov di, atb_devkit_cmd_output1
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_output2
    add si, 22
    call skip_spaces
    call .patch_customize_copy_payload
    call .patch_customize_emit_expr_from_buf
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_output2:
    mov di, atb_devkit_cmd_output2
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_output3
    add si, 12
    call skip_spaces
    call .patch_customize_copy_payload
    call .patch_customize_emit_expr_from_buf
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_output3:
    mov di, atb_devkit_cmd_output3
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_run1
    add si, 7
    call .patch_customize_copy_until_rparen
    mov bx, si
    mov si, atb_exec_buf
    call skip_spaces
    mov di, atb_tmp_token
    mov cx, 32
    call copy_token_limited
    mov si, bx
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_inline_output3_emit_expr
    call .patch_customize_find_arrow
    cmp ax, 1
    jne .patch_customize_inline_output3_emit_expr
    call skip_spaces
    call .patch_customize_copy_payload
    call .patch_customize_emit_expr_from_buf
    call .patch_customize_output3_maybe_read_input
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_output3_emit_expr:
    call .patch_customize_emit_expr_from_buf
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_run1:
    mov di, atb_devkit_cmd_run1
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_run2
    add si, 19
    call skip_spaces
    call .patch_customize_copy_payload
    mov si, atb_exec_buf
    call .patch_customize_run_command_buf
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_run2:
    mov di, atb_devkit_cmd_run2
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_clear
    add si, 16
    call skip_spaces
    call .patch_customize_copy_payload
    mov si, atb_exec_buf
    call .patch_customize_run_command_buf
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_clear:
    mov di, atb_devkit_cmd_clear
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_menu_title
    call clear_screen
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_menu_title:
    mov di, atb_devkit_cmd_menu_title
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_menu_item
    add si, 19
    call skip_spaces
    call .patch_customize_copy_payload
    mov bl, [cfg_color_frame]
    mov si, msg_atb_menu_frame
    call print_color_string
    mov bl, [cfg_color_ascii]
    mov si, atb_exec_buf
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_frame]
    mov si, msg_atb_menu_frame
    call print_color_string
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_menu_item:
    mov di, atb_devkit_cmd_menu_item
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_menu_input
    add si, 18
    call skip_spaces
    call .patch_customize_copy_payload
    mov bl, [cfg_color_info]
    mov si, msg_atb_menu_item_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_exec_buf
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_menu_input:
    mov di, atb_devkit_cmd_menu_input
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_write
    add si, 19
    call skip_spaces
    mov di, atb_var_name
    mov cx, 32
    call copy_token_limited
    mov bl, [cfg_color_info]
    mov si, msg_atb_menu_prompt
    call print_color_string
    mov di, atb_exec_buf
    mov word [input_limit], MAX_INPUT
    call read_line_limited
    mov si, atb_exec_buf
    mov di, atb_var_value
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    call .patch_customize_set_named_int
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_write:
    mov di, atb_devkit_cmd_write
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_append
    add si, 17
    call skip_spaces
    call .patch_customize_copy_payload
    mov si, atb_exec_buf
    call skip_spaces
    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited
    call skip_spaces
    cmp byte [si], ':'
    jne .patch_customize_inline_noop
    inc si
    cmp byte [si], ':'
    jne .patch_customize_inline_noop
    inc si
    call skip_spaces
    mov di, fs_token
    call fs_write_by_name
    cmp ax, 2
    jne .patch_customize_inline_write_done
    mov bl, [cfg_color_error]
    mov si, msg_fs_full
    call print_color_string
.patch_customize_inline_write_done:
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_append:
    mov di, atb_devkit_cmd_append
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_check_read
    add si, 18
    call skip_spaces
    call .patch_customize_copy_payload
    mov si, atb_exec_buf
    call skip_spaces
    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited
    call skip_spaces
    cmp byte [si], ':'
    jne .patch_customize_inline_noop
    inc si
    cmp byte [si], ':'
    jne .patch_customize_inline_noop
    inc si
    call skip_spaces
    mov di, fs_token
    call fs_append_by_name
    cmp ax, 2
    jne .patch_customize_inline_append_done
    mov bl, [cfg_color_error]
    mov si, msg_fs_full
    call print_color_string
.patch_customize_inline_append_done:
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_check_read:
    mov di, atb_devkit_cmd_read
    call strprefix
    cmp ax, 1
    jne .patch_customize_inline_noop
    add si, 16
    call skip_spaces
    call .patch_customize_copy_payload
    mov si, atb_exec_buf
    call skip_spaces
    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited
    mov si, fs_token
    call fs_validate_cat_path
    cmp ax, 1
    je .patch_customize_inline_read_try
    mov bl, [cfg_color_warn]
    mov si, msg_path_invalid
    call print_color_string
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_read_try:
    mov si, fs_token
    call fs_cat_by_name
    cmp ax, 1
    je .patch_customize_inline_read_done
    mov bl, [cfg_color_error]
    mov si, msg_file_not_found
    call print_color_string
.patch_customize_inline_read_done:
    mov ax, 1
    jmp .patch_customize_inline_done
.patch_customize_inline_noop:
    xor ax, ax
.patch_customize_inline_done:
    pop di
    pop cx
    pop bx
    ret
.patch_customize_run_command_buf:
    push ax
    push bx
    push cx
    push di
    push bp
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_run_done
    mov di, atb_tmp_token
    mov cx, 32
    call copy_token_limited
    mov si, atb_tmp_token
    mov di, runtime_python
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_python
    mov si, atb_tmp_token
    mov di, runtime_python3
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_python
    mov si, atb_tmp_token
    mov di, runtime_c
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_c
    mov si, atb_tmp_token
    mov di, runtime_generic
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_native
    mov si, atb_tmp_token
    mov di, atb_pkg1_runtime
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_pkg_runtime
    mov si, atb_tmp_token
    mov di, atb_pkg2_runtime
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_pkg_runtime
    mov si, atb_tmp_token
    mov di, atb_pkg3_runtime
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_pkg_runtime
    mov si, atb_tmp_token
    mov di, atb_pkg1_name
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_pkg1
    mov si, atb_tmp_token
    mov di, atb_pkg2_name
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_pkg2
    mov si, atb_tmp_token
    mov di, atb_pkg3_name
    call strcmp
    cmp ax, 1
    je .patch_customize_run_host_pkg3
    mov si, atb_exec_buf
    mov di, input_buffer
    mov cx, MAX_INPUT
    call copy_string_limited
    mov si, input_buffer
    call dispatch_command
    jmp .patch_customize_run_done
.patch_customize_run_host_python:
    mov bp, runtime_python
    jmp .patch_customize_run_host_emit
.patch_customize_run_host_c:
    mov bp, runtime_c
    jmp .patch_customize_run_host_emit
.patch_customize_run_host_native:
    mov bp, runtime_generic
    jmp .patch_customize_run_host_emit
.patch_customize_run_host_pkg_runtime:
    mov si, atb_tmp_token
    mov di, runtime_atbdevkit
    call strcmp
    cmp ax, 1
    je .patch_customize_run_done
    mov bp, atb_tmp_token
    jmp .patch_customize_run_host_emit
.patch_customize_run_host_pkg1:
    mov si, atb_pkg1_runtime
    mov di, runtime_atbdevkit
    call strcmp
    cmp ax, 1
    je .patch_customize_run_done
    mov bp, atb_pkg1_runtime
    jmp .patch_customize_run_host_emit
.patch_customize_run_host_pkg2:
    mov si, atb_pkg2_runtime
    mov di, runtime_atbdevkit
    call strcmp
    cmp ax, 1
    je .patch_customize_run_done
    mov bp, atb_pkg2_runtime
    jmp .patch_customize_run_host_emit
.patch_customize_run_host_pkg3:
    mov si, atb_pkg3_runtime
    mov di, runtime_atbdevkit
    call strcmp
    cmp ax, 1
    je .patch_customize_run_done
    mov bp, atb_pkg3_runtime
.patch_customize_run_host_emit:
    mov bl, [cfg_color_warn]
    mov si, msg_atb_run_host_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, bp
    call print_color_string
    mov bl, [cfg_color_warn]
    mov si, msg_atb_run_host_cmd
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_exec_buf
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
.patch_customize_run_done:
    pop bp
    pop di
    pop cx
    pop bx
    pop ax
    ret
.patch_customize_exec_write:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_append:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_read:
    call .patch_customize_exec_inline_stmt
    jmp .patch_customize_exec_continue
.patch_customize_exec_var:
    add si, 3
    call .patch_customize_skip_var_delims
    mov di, atb_var_name
    mov cx, 32
    call .patch_customize_copy_var_ident
    call .patch_customize_find_arrow
    cmp ax, 1
    jne .patch_customize_exec_continue
    call skip_spaces
    mov di, atb_devkit_expr_input
    call strprefix
    cmp ax, 1
    jne .patch_customize_exec_var_assign_expr
    mov di, atb_exec_buf
    mov word [input_limit], MAX_INPUT
    call read_line_limited
    mov si, atb_exec_buf
    mov di, atb_var_value
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    call .patch_customize_set_named_int
    jmp .patch_customize_exec_continue
.patch_customize_exec_var_assign_expr:
    call .patch_customize_copy_payload
    mov si, atb_exec_buf
    mov di, atb_var_value
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    call .patch_customize_set_named_int
    jmp .patch_customize_exec_continue
.patch_customize_skip_var_delims:
.patch_customize_skip_var_delims_loop:
    mov al, [si]
    cmp al, ' '
    je .patch_customize_skip_var_delims_inc
    cmp al, ':'
    je .patch_customize_skip_var_delims_inc
    ret
.patch_customize_skip_var_delims_inc:
    inc si
    jmp .patch_customize_skip_var_delims_loop
.patch_customize_copy_var_ident:
    cmp cx, 0
    jne .patch_customize_copy_var_ident_loop
    mov byte [di], 0
    ret
.patch_customize_copy_var_ident_loop:
    mov al, [si]
    cmp al, 0
    je .patch_customize_copy_var_ident_done
    cmp al, ' '
    je .patch_customize_copy_var_ident_done
    cmp al, ':'
    je .patch_customize_copy_var_ident_done
    cmp al, '='
    je .patch_customize_copy_var_ident_done
    cmp al, '>'
    je .patch_customize_copy_var_ident_done
    cmp al, '('
    je .patch_customize_copy_var_ident_done
    cmp al, ')'
    je .patch_customize_copy_var_ident_done
    mov [di], al
    inc di
    inc si
    dec cx
    jnz .patch_customize_copy_var_ident_loop
.patch_customize_copy_var_ident_skip_tail:
    mov al, [si]
    cmp al, 0
    je .patch_customize_copy_var_ident_done
    cmp al, ' '
    je .patch_customize_copy_var_ident_done
    cmp al, ':'
    je .patch_customize_copy_var_ident_done
    cmp al, '='
    je .patch_customize_copy_var_ident_done
    cmp al, '>'
    je .patch_customize_copy_var_ident_done
    cmp al, '('
    je .patch_customize_copy_var_ident_done
    cmp al, ')'
    je .patch_customize_copy_var_ident_done
    inc si
    jmp .patch_customize_copy_var_ident_skip_tail
.patch_customize_copy_var_ident_done:
    mov byte [di], 0
    ret
.patch_customize_find_arrow:
    push bx
.patch_customize_find_arrow_loop:
    mov al, [si]
    cmp al, 0
    je .patch_customize_find_arrow_no
    cmp al, '='
    jne .patch_customize_find_arrow_next
    mov bx, si
    inc bx
.patch_customize_find_arrow_skip_spaces:
    cmp byte [bx], ' '
    jne .patch_customize_find_arrow_check_gt
    inc bx
    jmp .patch_customize_find_arrow_skip_spaces
.patch_customize_find_arrow_check_gt:
    cmp byte [bx], '>'
    jne .patch_customize_find_arrow_next
    mov si, bx
    inc si
    mov ax, 1
    jmp .patch_customize_find_arrow_done
.patch_customize_find_arrow_next:
    inc si
    jmp .patch_customize_find_arrow_loop
.patch_customize_find_arrow_no:
    xor ax, ax
.patch_customize_find_arrow_done:
    pop bx
    ret
.patch_customize_copy_until_rparen:
    push ax
    push cx
    push di
    mov di, atb_exec_buf
    mov cx, FS_TEXT_MAX
.patch_customize_copy_until_rparen_loop:
    cmp cx, 0
    je .patch_customize_copy_until_rparen_done
    mov al, [si]
    cmp al, 0
    je .patch_customize_copy_until_rparen_done
    cmp al, ')'
    je .patch_customize_copy_until_rparen_close
    mov [di], al
    inc di
    dec cx
    inc si
    jmp .patch_customize_copy_until_rparen_loop
.patch_customize_copy_until_rparen_close:
    inc si
.patch_customize_copy_until_rparen_done:
    mov byte [di], 0
    pop di
    pop cx
    pop ax
    ret
.patch_customize_set_named_int:
    mov si, atb_var_name
    mov di, atb_name_a
    call strcmp
    cmp ax, 1
    jne .patch_customize_set_named_int_check_b
    mov si, atb_var_value
    call .patch_customize_parse_u16
    mov [atb_int_a], ax
    ret
.patch_customize_set_named_int_check_b:
    mov si, atb_var_name
    mov di, atb_name_b
    call strcmp
    cmp ax, 1
    jne .patch_customize_set_named_int_check_choice
    mov si, atb_var_value
    call .patch_customize_parse_u16
    mov [atb_int_b], ax
    ret
.patch_customize_set_named_int_check_choice:
    mov si, atb_var_name
    mov di, atb_name_user_choice
    call strcmp
    cmp ax, 1
    jne .patch_customize_set_named_int_done
    mov si, atb_var_value
    call .patch_customize_parse_u16
    mov [atb_int_user_choice], ax
.patch_customize_set_named_int_done:
    ret
.patch_customize_output3_maybe_read_input:
    mov si, atb_tmp_token
    cmp byte [si], 0
    je .patch_customize_output3_input_done
    mov di, atb_name_a
    call strcmp
    cmp ax, 1
    je .patch_customize_output3_read_a
    mov si, atb_tmp_token
    mov di, atb_name_b
    call strcmp
    cmp ax, 1
    je .patch_customize_output3_read_b
    mov si, atb_tmp_token
    mov di, atb_name_user_choice
    call strcmp
    cmp ax, 1
    je .patch_customize_output3_read_choice
    mov si, atb_tmp_token
    mov di, atb_var_name
    call strcmp
    cmp ax, 1
    jne .patch_customize_output3_input_done
    mov di, atb_exec_buf
    mov word [input_limit], MAX_INPUT
    call read_line_limited
    mov si, atb_exec_buf
    mov di, atb_var_value
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    call .patch_customize_set_named_int
    jmp .patch_customize_output3_input_done
.patch_customize_output3_read_a:
    mov di, atb_exec_buf
    mov word [input_limit], MAX_INPUT
    call read_line_limited
    mov si, atb_exec_buf
    call .patch_customize_parse_u16
    mov [atb_int_a], ax
    jmp .patch_customize_output3_input_done
.patch_customize_output3_read_b:
    mov di, atb_exec_buf
    mov word [input_limit], MAX_INPUT
    call read_line_limited
    mov si, atb_exec_buf
    call .patch_customize_parse_u16
    mov [atb_int_b], ax
    jmp .patch_customize_output3_input_done
.patch_customize_output3_read_choice:
    mov di, atb_exec_buf
    mov word [input_limit], MAX_INPUT
    call read_line_limited
    mov si, atb_exec_buf
    call .patch_customize_parse_u16
    mov [atb_int_user_choice], ax
.patch_customize_output3_input_done:
    ret
.patch_customize_get_named_int:
    mov di, atb_name_a
    call strcmp
    cmp ax, 1
    jne .patch_customize_get_named_int_check_b
    mov ax, [atb_int_a]
    mov dx, 1
    ret
.patch_customize_get_named_int_check_b:
    mov di, atb_name_b
    call strcmp
    cmp ax, 1
    jne .patch_customize_get_named_int_check_choice
    mov ax, [atb_int_b]
    mov dx, 1
    ret
.patch_customize_get_named_int_check_choice:
    mov di, atb_name_user_choice
    call strcmp
    cmp ax, 1
    jne .patch_customize_get_named_int_check_var
    mov ax, [atb_int_user_choice]
    mov dx, 1
    ret
.patch_customize_get_named_int_check_var:
    mov di, atb_var_name
    call strcmp
    cmp ax, 1
    jne .patch_customize_get_named_int_no
    mov si, atb_var_value
    call .patch_customize_parse_u16
    mov dx, 1
    ret
.patch_customize_get_named_int_no:
    xor ax, ax
    xor dx, dx
    ret
.patch_customize_emit_expr_from_buf:
    mov si, atb_exec_buf
    call skip_spaces
    cmp byte [si], 0
    je .patch_customize_emit_expr_done
    mov di, atb_var_name
    call strcmp
    cmp ax, 1
    jne .patch_customize_emit_expr_check_num_a
    mov bl, [cfg_color_info]
    mov si, atb_var_value
    call print_color_string
    jmp .patch_customize_emit_expr_newline
.patch_customize_emit_expr_check_num_a:
    mov si, atb_exec_buf
    call skip_spaces
    mov di, atb_name_a
    call strcmp
    cmp ax, 1
    jne .patch_customize_emit_expr_check_num_b
    mov bl, [cfg_color_info]
    mov ax, [atb_int_a]
    call print_u16
    jmp .patch_customize_emit_expr_newline
.patch_customize_emit_expr_check_num_b:
    mov si, atb_exec_buf
    call skip_spaces
    mov di, atb_name_b
    call strcmp
    cmp ax, 1
    jne .patch_customize_emit_expr_check_num_choice
    mov bl, [cfg_color_info]
    mov ax, [atb_int_b]
    call print_u16
    jmp .patch_customize_emit_expr_newline
.patch_customize_emit_expr_check_num_choice:
    mov si, atb_exec_buf
    call skip_spaces
    mov di, atb_name_user_choice
    call strcmp
    cmp ax, 1
    jne .patch_customize_emit_expr_eval
    mov bl, [cfg_color_info]
    mov ax, [atb_int_user_choice]
    call print_u16
    jmp .patch_customize_emit_expr_newline
.patch_customize_emit_expr_eval:
    mov si, atb_exec_buf
    call skip_spaces
    call .patch_customize_eval_int_expr
    cmp dx, 1
    jne .patch_customize_emit_expr_raw
    mov bl, [cfg_color_info]
    call print_u16
    jmp .patch_customize_emit_expr_newline
.patch_customize_emit_expr_raw:
    mov bl, [cfg_color_info]
    mov si, atb_exec_buf
    call print_color_string
.patch_customize_emit_expr_newline:
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
.patch_customize_emit_expr_done:
    ret
.patch_customize_parse_u16:
    push bx
    xor ax, ax
    call skip_spaces
.patch_customize_parse_u16_loop:
    mov bl, [si]
    cmp bl, '0'
    jb .patch_customize_parse_u16_done
    cmp bl, '9'
    ja .patch_customize_parse_u16_done
    mov bx, ax
    shl ax, 1
    shl bx, 3
    add ax, bx
    mov bl, [si]
    sub bl, '0'
    xor bh, bh
    add ax, bx
    inc si
    jmp .patch_customize_parse_u16_loop
.patch_customize_parse_u16_done:
    pop bx
    ret
.patch_customize_eval_int_expr:
    push bx
    push cx
    call .patch_customize_parse_operand
    cmp dx, 1
    jne .patch_customize_eval_int_expr_fail
    mov cx, ax
    call skip_spaces
    mov bl, [si]
    cmp bl, 0
    je .patch_customize_eval_int_expr_single
    cmp bl, '+'
    je .patch_customize_eval_int_expr_op
    cmp bl, '-'
    je .patch_customize_eval_int_expr_op
    cmp bl, '*'
    je .patch_customize_eval_int_expr_op
    cmp bl, '/'
    je .patch_customize_eval_int_expr_op
    cmp bl, 92
    je .patch_customize_eval_int_expr_op
    jmp .patch_customize_eval_int_expr_fail
.patch_customize_eval_int_expr_op:
    push bx
    inc si
    call .patch_customize_parse_operand
    pop bx
    cmp dx, 1
    jne .patch_customize_eval_int_expr_fail
    mov dx, ax
    mov ax, cx
    cmp bl, '+'
    jne .patch_customize_eval_int_expr_check_sub
    add ax, dx
    jmp .patch_customize_eval_int_expr_ok
.patch_customize_eval_int_expr_check_sub:
    cmp bl, '-'
    jne .patch_customize_eval_int_expr_check_mul
    sub ax, dx
    jmp .patch_customize_eval_int_expr_ok
.patch_customize_eval_int_expr_check_mul:
    cmp bl, '*'
    jne .patch_customize_eval_int_expr_check_div
    mul dx
    jmp .patch_customize_eval_int_expr_ok
.patch_customize_eval_int_expr_check_div:
    cmp dx, 0
    je .patch_customize_eval_int_expr_fail
    mov bx, dx
    xor dx, dx
    div bx
    jmp .patch_customize_eval_int_expr_ok
.patch_customize_eval_int_expr_single:
    mov ax, cx
.patch_customize_eval_int_expr_ok:
    mov dx, 1
    pop cx
    pop bx
    ret
.patch_customize_eval_int_expr_fail:
    xor ax, ax
    xor dx, dx
    pop cx
    pop bx
    ret
.patch_customize_parse_operand:
    call skip_spaces
    mov al, [si]
    cmp al, 0
    je .patch_customize_parse_operand_fail
    cmp al, '0'
    jb .patch_customize_parse_operand_name
    cmp al, '9'
    ja .patch_customize_parse_operand_name
    call .patch_customize_parse_u16
    mov dx, 1
    ret
.patch_customize_parse_operand_name:
    push bx
    push cx
    push di
    mov di, atb_tmp_token
    mov cx, 32
.patch_customize_parse_operand_name_loop:
    mov al, [si]
    cmp al, 0
    je .patch_customize_parse_operand_name_done
    cmp al, ' '
    je .patch_customize_parse_operand_name_done
    cmp al, '+'
    je .patch_customize_parse_operand_name_done
    cmp al, '-'
    je .patch_customize_parse_operand_name_done
    cmp al, '*'
    je .patch_customize_parse_operand_name_done
    cmp al, '/'
    je .patch_customize_parse_operand_name_done
    cmp al, 92
    je .patch_customize_parse_operand_name_done
    cmp al, ')'
    je .patch_customize_parse_operand_name_done
    cmp al, ';'
    je .patch_customize_parse_operand_name_done
    cmp cx, 0
    je .patch_customize_parse_operand_name_skip_store
    mov [di], al
    inc di
    dec cx
.patch_customize_parse_operand_name_skip_store:
    inc si
    jmp .patch_customize_parse_operand_name_loop
.patch_customize_parse_operand_name_done:
    mov byte [di], 0
    mov bx, si
    mov si, atb_tmp_token
    call .patch_customize_get_named_int
    mov si, bx
    pop di
    pop cx
    pop bx
    ret
.patch_customize_parse_operand_fail:
    xor ax, ax
    xor dx, dx
    ret
.patch_customize_exec_continue:
    mov si, [atb_exec_src_ptr]
    jmp .patch_customize_exec_line
.patch_customize_copy_payload:
    push ax
    push cx
    push di
    mov di, atb_exec_buf
    mov cx, FS_TEXT_MAX
    cmp byte [si], '"'
    jne .patch_customize_copy_payload_raw
    inc si
.patch_customize_copy_payload_qloop:
    cmp cx, 0
    je .patch_customize_copy_payload_done
    mov al, [si]
    cmp al, 0
    je .patch_customize_copy_payload_done
    cmp al, '"'
    je .patch_customize_copy_payload_qend
    mov [di], al
    inc di
    dec cx
    inc si
    jmp .patch_customize_copy_payload_qloop
.patch_customize_copy_payload_qend:
    inc si
    jmp .patch_customize_copy_payload_done
.patch_customize_copy_payload_raw:
.patch_customize_copy_payload_rloop:
    cmp cx, 0
    je .patch_customize_copy_payload_done
    mov al, [si]
    cmp al, 0
    je .patch_customize_copy_payload_done
    cmp al, 13
    je .patch_customize_copy_payload_done
    cmp al, 10
    je .patch_customize_copy_payload_done
    mov [di], al
    inc di
    dec cx
    inc si
    jmp .patch_customize_copy_payload_rloop
.patch_customize_copy_payload_done:
    mov byte [di], 0
    pop di
    pop cx
    pop ax
    ret
.patch_customize_exec_source_done:
    call fs_store_save
    pop di
    pop dx
    pop cx
    pop bx
    pop ax
    ret
.patch_customize_install_program:
    mov si, atb_arg_name
    mov di, fs_name_cscript
    call strcmp
    cmp ax, 1
    jne .patch_customize_install_check_existing
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_core_present
    call print_color_string
    ret
.patch_customize_install_check_existing:
    mov di, atb_pkg1_name
    call strcmp
    cmp ax, 1
    je .patch_customize_install_exists
    mov di, atb_pkg2_name
    call strcmp
    cmp ax, 1
    je .patch_customize_install_exists
    mov di, atb_pkg3_name
    call strcmp
    cmp ax, 1
    je .patch_customize_install_exists
    cmp byte [atb_pkg1_name], 0
    je .patch_customize_install_slot1
    cmp byte [atb_pkg2_name], 0
    je .patch_customize_install_slot2
    cmp byte [atb_pkg3_name], 0
    je .patch_customize_install_slot3
    mov bl, COLOR_ERROR
    mov si, msg_atbman_install_full
    call print_color_string
    ret
.patch_customize_install_exists:
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_install_exists_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_arg_name
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    call fs_store_save
    ret
.patch_customize_install_slot1:
    mov si, atb_arg_name
    mov di, atb_pkg1_name
    mov cx, 32
    call copy_string_limited
    mov si, atb_arg_source
    mov di, atb_pkg1_source
    mov cx, 64
    call copy_string_limited
    mov si, atb_arg_runtime
    mov di, atb_pkg1_runtime
    mov cx, 15
    call copy_string_limited
    jmp .patch_customize_install_ok
.patch_customize_install_slot2:
    mov si, atb_arg_name
    mov di, atb_pkg2_name
    mov cx, 32
    call copy_string_limited
    mov si, atb_arg_source
    mov di, atb_pkg2_source
    mov cx, 64
    call copy_string_limited
    mov si, atb_arg_runtime
    mov di, atb_pkg2_runtime
    mov cx, 15
    call copy_string_limited
    jmp .patch_customize_install_ok
.patch_customize_install_slot3:
    mov si, atb_arg_name
    mov di, atb_pkg3_name
    mov cx, 32
    call copy_string_limited
    mov si, atb_arg_source
    mov di, atb_pkg3_source
    mov cx, 64
    call copy_string_limited
    mov si, atb_arg_runtime
    mov di, atb_pkg3_runtime
    mov cx, 15
    call copy_string_limited
.patch_customize_install_ok:
    mov bl, [cfg_color_info]
    mov si, msg_atbman_install_ok_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_arg_name
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_install_from
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_arg_source
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_install_runtime
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_arg_runtime
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    ret
.patch_customize_uninstall_program:
    mov si, atb_arg_name
    mov di, fs_name_cscript
    call strcmp
    cmp ax, 1
    jne .patch_customize_uninstall_check_slot1
    mov bl, COLOR_ERROR
    mov si, msg_atbman_core_protected
    call print_color_string
    ret
.patch_customize_uninstall_check_slot1:
    mov di, atb_pkg1_name
    call strcmp
    cmp ax, 1
    je .patch_customize_uninstall_slot1
    mov di, atb_pkg2_name
    call strcmp
    cmp ax, 1
    je .patch_customize_uninstall_slot2
    mov di, atb_pkg3_name
    call strcmp
    cmp ax, 1
    je .patch_customize_uninstall_slot3
    mov bl, COLOR_ERROR
    mov si, msg_atbman_uninstall_missing_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_arg_name
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    ret
.patch_customize_uninstall_slot1:
    mov byte [atb_pkg1_name], 0
    mov byte [atb_pkg1_source], 0
    mov byte [atb_pkg1_runtime], 0
    jmp .patch_customize_uninstall_ok
.patch_customize_uninstall_slot2:
    mov byte [atb_pkg2_name], 0
    mov byte [atb_pkg2_source], 0
    mov byte [atb_pkg2_runtime], 0
    jmp .patch_customize_uninstall_ok
.patch_customize_uninstall_slot3:
    mov byte [atb_pkg3_name], 0
    mov byte [atb_pkg3_source], 0
    mov byte [atb_pkg3_runtime], 0
.patch_customize_uninstall_ok:
    mov bl, [cfg_color_info]
    mov si, msg_atbman_uninstall_ok_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_arg_name
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    ret
.patch_customize_list_programs:
    mov bl, [cfg_color_accent]
    mov si, msg_atbman_list_title
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, fs_name_cscript
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_list_sep
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_source_core
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_list_runtime_sep
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, runtime_atbdevkit
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    xor dl, dl
    cmp byte [atb_pkg1_name], 0
    je .patch_customize_list_slot2
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg1_name
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_list_sep
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg1_source
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_list_runtime_sep
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg1_runtime
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    inc dl
.patch_customize_list_slot2:
    cmp byte [atb_pkg2_name], 0
    je .patch_customize_list_slot3
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg2_name
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_list_sep
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg2_source
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_list_runtime_sep
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg2_runtime
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    inc dl
.patch_customize_list_slot3:
    cmp byte [atb_pkg3_name], 0
    je .patch_customize_list_finish
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg3_name
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_list_sep
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg3_source
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_atbman_list_runtime_sep
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov si, atb_pkg3_runtime
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    inc dl
.patch_customize_list_finish:
    cmp dl, 0
    jne .patch_customize_list_done
    mov bl, [cfg_color_warn]
    mov si, msg_atbman_list_none
    call print_color_string
.patch_customize_list_done:
    ret
.patch_customize_apply_cscript_profile:
    mov byte [cfg_banner_enabled], 1
    mov byte [cfg_prompt_compact], 1
    mov byte [cfg_theme_index], 2
    call .patch_customize_theme_2
    ret
.patch_customize_cycle_theme:
    mov al, [cfg_theme_index]
    inc al
    cmp al, 3
    jb .patch_customize_cycle_store
    xor al, al
.patch_customize_cycle_store:
    mov [cfg_theme_index], al
    cmp al, 0
    je .patch_customize_theme_0
    cmp al, 1
    je .patch_customize_theme_1
    jmp .patch_customize_theme_2
.patch_customize_theme_0:
    mov byte [cfg_color_default], 0x07
    mov byte [cfg_color_info], 0x0B
    mov byte [cfg_color_warn], 0x0E
    mov byte [cfg_color_error], 0x0C
    mov byte [cfg_color_prompt], 0x0A
    mov byte [cfg_color_ascii], 0x0D
    mov byte [cfg_color_frame], 0x09
    mov byte [cfg_color_accent], 0x03
    ret
.patch_customize_theme_1:
    mov byte [cfg_color_default], 0x07
    mov byte [cfg_color_info], 0x0F
    mov byte [cfg_color_warn], 0x0B
    mov byte [cfg_color_error], 0x0C
    mov byte [cfg_color_prompt], 0x0B
    mov byte [cfg_color_ascii], 0x0F
    mov byte [cfg_color_frame], 0x0B
    mov byte [cfg_color_accent], 0x09
    ret
.patch_customize_theme_2:
    mov byte [cfg_color_default], 0x07
    mov byte [cfg_color_info], 0x0E
    mov byte [cfg_color_warn], 0x06
    mov byte [cfg_color_error], 0x0C
    mov byte [cfg_color_prompt], 0x0E
    mov byte [cfg_color_ascii], 0x06
    mov byte [cfg_color_frame], 0x06
    mov byte [cfg_color_accent], 0x0C
    ret
.patch_customize_openact:
    call clear_screen
.patch_customize_openact_redraw:
    mov bl, [cfg_color_ascii]
    mov si, msg_openact_title
    call print_color_string
    mov bl, [cfg_color_warn]
    mov si, msg_openact_credit
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_openact_banner
    call print_color_string
    mov bl, [cfg_color_prompt]
    cmp byte [cfg_banner_enabled], 1
    jne .patch_customize_openact_banner_off
    mov si, msg_openact_on
    call print_color_string
    jmp .patch_customize_openact_banner_tail
.patch_customize_openact_banner_off:
    mov si, msg_openact_off
    call print_color_string
.patch_customize_openact_banner_tail:
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_openact_theme
    call print_color_string
    mov bl, [cfg_color_prompt]
    call .patch_customize_openact_print_theme
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_openact_prompt
    call print_color_string
    mov bl, [cfg_color_prompt]
    cmp byte [cfg_prompt_compact], 1
    jne .patch_customize_openact_prompt_classic
    mov si, msg_openact_prompt_compact
    call print_color_string
    jmp .patch_customize_openact_prompt_tail
.patch_customize_openact_prompt_classic:
    mov si, msg_openact_prompt_classic
    call print_color_string
.patch_customize_openact_prompt_tail:
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_openact_user
    call print_color_string
    mov bl, [cfg_color_prompt]
    cmp byte [username], 0
    jne .patch_customize_openact_user_named
    mov si, default_user
    call print_color_string
    jmp .patch_customize_openact_user_tail
.patch_customize_openact_user_named:
    mov si, username
    call print_color_string
.patch_customize_openact_user_tail:
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_openact_opt_readme
    call print_color_string
    mov si, msg_openact_opt_judges
    call print_color_string
    mov si, msg_openact_opt_unknown
    call print_color_string
    mov bl, [cfg_color_warn]
    mov si, msg_openact_keys
    call print_color_string
.patch_customize_openact_wait_key:
    mov ah, 0x00
    int 0x16
    cmp al, '1'
    je .patch_customize_openact_toggle_banner
    cmp al, '2'
    je .patch_customize_openact_cycle_theme
    cmp al, '3'
    je .patch_customize_openact_toggle_prompt
    cmp al, '4'
    je .patch_customize_openact_edit_user
    cmp al, '5'
    je .patch_customize_openact_edit_readme
    cmp al, '6'
    je .patch_customize_openact_edit_judges
    cmp al, '7'
    je .patch_customize_openact_edit_unknown
    cmp al, 'r'
    je .patch_customize_openact_reset_profile
    cmp al, 'R'
    je .patch_customize_openact_reset_profile
    cmp al, 's'
    je .patch_customize_openact_save_exit
    cmp al, 'S'
    je .patch_customize_openact_save_exit
    cmp al, 'q'
    je .patch_customize_openact_save_exit
    cmp al, 'Q'
    je .patch_customize_openact_save_exit
    cmp al, 27
    je .patch_customize_openact_save_exit
    jmp .patch_customize_openact_wait_key
.patch_customize_openact_toggle_banner:
    mov al, [cfg_banner_enabled]
    xor al, 1
    mov [cfg_banner_enabled], al
    jmp .patch_customize_openact_redraw
.patch_customize_openact_cycle_theme:
    call .patch_customize_cycle_theme
    jmp .patch_customize_openact_redraw
.patch_customize_openact_toggle_prompt:
    mov al, [cfg_prompt_compact]
    xor al, 1
    mov [cfg_prompt_compact], al
    jmp .patch_customize_openact_redraw
.patch_customize_openact_edit_user:
    call clear_screen
    mov bl, [cfg_color_accent]
    mov si, msg_openact_enter_user
    call print_color_string
    mov di, username
    mov word [input_limit], USER_MAX
    call read_line_limited
    cmp byte [username], 0
    jne .patch_customize_openact_edit_user_done
    mov si, default_user
    mov di, username
    call copy_string
.patch_customize_openact_edit_user_done:
    mov byte [user_initialized], 1
    jmp .patch_customize_openact_redraw
.patch_customize_openact_edit_readme:
    call clear_screen
    mov bl, [cfg_color_accent]
    mov si, msg_openact_enter_readme
    call print_color_string
    mov di, fs_readme
    mov word [input_limit], FS_TEXT_MAX
    call read_line_limited
    cmp byte [fs_readme], 0
    jne .patch_customize_openact_redraw
    mov si, fs_readme_default
    mov di, fs_readme
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    jmp .patch_customize_openact_redraw
.patch_customize_openact_edit_judges:
    call clear_screen
    mov bl, [cfg_color_accent]
    mov si, msg_openact_enter_judges
    call print_color_string
    mov di, fs_judges
    mov word [input_limit], FS_TEXT_MAX
    call read_line_limited
    cmp byte [fs_judges], 0
    jne .patch_customize_openact_redraw
    mov si, fs_judges_default
    mov di, fs_judges
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    jmp .patch_customize_openact_redraw
.patch_customize_openact_edit_unknown:
    call clear_screen
    mov bl, [cfg_color_accent]
    mov si, msg_openact_enter_unknown
    call print_color_string
    mov di, msg_unknown
    mov word [input_limit], 63
    call read_line_limited
    cmp byte [msg_unknown], 0
    jne .patch_customize_openact_redraw
    mov si, msg_atbman_unknown_fallback
    mov di, msg_unknown
    mov cx, 63
    call copy_string_limited
    jmp .patch_customize_openact_redraw
.patch_customize_openact_reset_profile:
    call .patch_customize_apply_cscript_profile
    mov si, fs_readme_default
    mov di, fs_readme
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov si, fs_judges_default
    mov di, fs_judges
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov si, msg_atbman_unknown_fallback
    mov di, msg_unknown
    mov cx, 63
    call copy_string_limited
    mov bl, [cfg_color_info]
    mov si, msg_openact_reset_done
    call print_color_string
    jmp .patch_customize_openact_wait_key
.patch_customize_openact_save_exit:
    call fs_store_save
    call clear_screen
    call show_banner
    mov bl, [cfg_color_info]
    mov si, msg_openact_saved
    call print_color_string
    ret
.patch_customize_openact_print_theme:
    mov al, [cfg_theme_index]
    cmp al, 0
    je .patch_customize_openact_theme0
    cmp al, 1
    je .patch_customize_openact_theme1
    mov si, msg_openact_theme_amber
    call print_color_string
    ret
.patch_customize_openact_theme0:
    mov si, msg_openact_theme_classic
    call print_color_string
    ret
.patch_customize_openact_theme1:
    mov si, msg_openact_theme_ice
    call print_color_string
    ret
.patch_customize_dispatch_continue:

    cmp byte [msg_unknown], 0
    jne .unknown_ready
    mov si, msg_unknown_default
    mov di, msg_unknown
    mov cx, 63
    call copy_string_limited
.unknown_ready:

    mov bl, COLOR_ERROR
    mov si, msg_unknown
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.help:
    call show_help
    jmp .done

.about:
    call show_about
    jmp .done

.clear:
    call clear_screen
    call show_banner
    jmp .done

.banner:
    add si, 6
    call skip_spaces
    cmp byte [si], 0
    je .banner_show
    mov di, cmd_clear
    call strcmp
    cmp ax, 1
    je .banner_clear_only
    mov di, arg_full
    call strcmp
    cmp ax, 1
    je .clear
    mov bl, COLOR_WARN
    mov si, msg_banner_usage
    call print_color_string
    jmp .done

.banner_show:
    call show_banner
    jmp .done

.banner_clear_only:
    call clear_screen
    jmp .done

.patches:
    add si, 7
    call skip_spaces
    cmp byte [si], 0
    je .patches_show
    mov di, arg_raw
    call strcmp
    cmp ax, 1
    je .patches_raw
    mov bl, COLOR_WARN
    mov si, msg_patches_usage
    call print_color_string
    jmp .done

.patches_show:
    call show_patches
    jmp .done

.patches_raw:
    call show_patches_raw
    jmp .done

.sys:
    add si, 3
    call skip_spaces
    cmp byte [si], 0
    je .sys_usage
    mov di, arg_info
    call strcmp
    cmp ax, 1
    je .about
    mov di, cmd_time
    call strcmp
    cmp ax, 1
    je .time
    mov di, cmd_date
    call strcmp
    cmp ax, 1
    je .date
    mov di, cmd_uptime
    call strcmp
    cmp ax, 1
    je .uptime
    mov di, cmd_version
    call strcmp
    cmp ax, 1
    je .version
    mov di, cmd_fetch
    call strcmp
    cmp ax, 1
    je .fetch
    mov di, cmd_patches
    call strcmp
    cmp ax, 1
    je .patches_show
    mov di, cmd_banner
    call strcmp
    cmp ax, 1
    je .banner_show

.sys_usage:
    mov bl, COLOR_WARN
    mov si, msg_sys_usage
    call print_color_string
    jmp .done

.uptime:
    call show_uptime
    jmp .done

.time:
    call show_time
    jmp .done

.date:
    call show_date
    jmp .done

.version:
    call show_version
    jmp .done

.fetch:
    call show_fetch
    jmp .done

.exit:
    call fs_store_save
    call exit_cmd
    jmp .done

.echo:
    add si, 4
    call skip_spaces
    cmp byte [si], 0
    je .echo_usage

    cmp byte [si], '-'
    jne .echo_plain
    cmp byte [si + 2], ' '
    jne .echo_plain
    mov al, [si + 1]
    cmp al, 'n'
    je .echo_no_newline
    cmp al, 'u'
    je .echo_upper
    cmp al, 'l'
    je .echo_lower
    cmp al, 'h'
    je .echo_usage
    jmp .echo_plain

.echo_no_newline:
    add si, 2
    call skip_spaces
    cmp byte [si], 0
    je .done
    mov bl, COLOR_INFO
    call print_color_string
    jmp .done

.echo_upper:
    add si, 2
    call skip_spaces
    cmp byte [si], 0
    je .echo_usage
    mov bl, COLOR_INFO
    call print_upper_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.echo_lower:
    add si, 2
    call skip_spaces
    cmp byte [si], 0
    je .echo_usage
    mov bl, COLOR_INFO
    call print_lower_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.echo_plain:
    mov bl, COLOR_INFO
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.echo_usage:
    mov bl, COLOR_WARN
    mov si, msg_echo_usage
    call print_color_string
    jmp .done

.setname:
    add si, 7
    call skip_spaces
    cmp byte [si], 0
    je .setname_show

    mov di, arg_reset
    call strcmp
    cmp ax, 1
    je .setname_reset

    mov di, arg_dash_h
    call strcmp
    cmp ax, 1
    je .setname_usage

    mov di, arg_dash_dash_help
    call strcmp
    cmp ax, 1
    je .setname_usage

    mov di, username
    mov cx, USER_MAX
    call copy_string_limited
    mov byte [user_initialized], 1
    mov bl, COLOR_INFO
    mov si, msg_setname_ok_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, username
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    call fs_store_save
    jmp .done

.setname_show:
    mov bl, COLOR_ACCENT
    mov si, msg_current_user_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    cmp byte [username], 0
    jne .setname_show_name
    mov si, default_user
    call print_color_string
    jmp .setname_show_tail
.setname_show_name:
    mov si, username
    call print_color_string
.setname_show_tail:
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.setname_reset:
    mov si, default_user
    mov di, username
    call copy_string
    mov byte [user_initialized], 1
    mov bl, COLOR_INFO
    mov si, msg_setname_reset
    call print_color_string
    call fs_store_save
    jmp .done

.setname_usage:
    mov bl, COLOR_WARN
    mov si, msg_setname_usage
    call print_color_string
    jmp .done

.region:
    add si, 6
    call skip_spaces
    cmp byte [si], 0
    je .region_show
    mov di, arg_set
    call strcmp
    cmp ax, 1
    je .region_set
    mov di, arg_dash_h
    call strcmp
    cmp ax, 1
    je .region_usage
    mov di, arg_dash_dash_help
    call strcmp
    cmp ax, 1
    je .region_usage
    jmp .region_usage

.region_set:
    call region_setup_interactive
    call fs_store_save
    jmp .done

.region_show:
    call show_region
    jmp .done

.region_usage:
    mov bl, COLOR_WARN
    mov si, msg_region_usage
    call print_color_string
    jmp .done

.passwd:
    add si, 6
    call skip_spaces
    cmp byte [si], 0
    je .passwd_set
    mov di, arg_dash_h
    call strcmp
    cmp ax, 1
    je .passwd_usage
    mov di, arg_dash_dash_help
    call strcmp
    cmp ax, 1
    je .passwd_usage
    jmp .passwd_usage

.passwd_set:
    call password_setup_interactive
    call fs_store_save
    jmp .done

.passwd_usage:
    mov bl, COLOR_WARN
    mov si, msg_passwd_usage
    call print_color_string
    jmp .done

.cd:
    add si, 2
    call skip_spaces
    cmp byte [si], 0
    je .cd_show
    mov di, fs_token
    mov cx, FS_NAME_MAX - 1
    call copy_token_limited
    call skip_spaces
    cmp byte [si], 0
    jne .cd_usage

    mov si, fs_token
    mov di, arg_root
    call strcmp
    cmp ax, 1
    je .cd_root
    mov di, arg_dotdot
    call strcmp
    cmp ax, 1
    je .cd_root

    mov si, fs_token
    call fs_dir_exists
    cmp ax, 1
    jne .cd_not_found

    mov si, fs_token
    mov di, current_dir
    mov cx, FS_NAME_MAX - 1
    call copy_string_limited
    call fs_store_save
    jmp .cd_show

.cd_root:
    mov byte [current_dir], 0
    call fs_store_save
    jmp .cd_show

.cd_show:
    mov bl, COLOR_ACCENT
    mov si, msg_cd_now
    call print_color_string
    mov bl, COLOR_PROMPT
    cmp byte [current_dir], 0
    jne .cd_show_named
    mov si, arg_root
    call print_color_string
    jmp .cd_show_tail
.cd_show_named:
    mov al, '/'
    call putc_color
    mov si, current_dir
    call print_color_string
.cd_show_tail:
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.cd_not_found:
    mov bl, COLOR_ERROR
    mov si, msg_cd_not_found
    call print_color_string
    jmp .done

.cd_usage:
    mov bl, COLOR_WARN
    mov si, msg_cd_usage
    call print_color_string
    jmp .done

.reboot:
    call fs_store_save
    call clear_screen
    call show_banner
    call show_boot_notice
    jmp .done

.fsls:
    call fs_list
    jmp .done

.fsinfo:
    call fs_info
    jmp .done

.fswrite:
    add si, 7
    call skip_spaces
    cmp byte [si], 0
    je .fswrite_usage

    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited
    call skip_spaces
    cmp byte [si], 0
    je .fswrite_usage

    mov si, fs_token
    call fs_resolve_with_cwd
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_validate_file_path
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_parent_ready_for_file
    cmp ax, 1
    jne .dir_missing

    mov di, fs_token
    call fs_write_by_name
    cmp ax, 1
    je .done
    cmp ax, 2
    je .fs_full

    mov bl, COLOR_ERROR
    mov si, msg_file_not_found
    call print_color_string
    jmp .done

.append:
    add si, 6
    call skip_spaces
    cmp byte [si], 0
    je .append_usage

    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited
    call skip_spaces
    cmp byte [si], 0
    je .append_usage

    mov si, fs_token
    call fs_resolve_with_cwd
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_validate_file_path
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_parent_ready_for_file
    cmp ax, 1
    jne .dir_missing

    mov di, fs_token
    call fs_append_by_name
    cmp ax, 1
    je .done
    cmp ax, 2
    je .fs_full

    mov bl, COLOR_ERROR
    mov si, msg_file_not_found
    call print_color_string
    jmp .done

.rmfile:
    add si, 2
    call skip_spaces
    cmp byte [si], 0
    je .rm_usage

    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited
    mov si, fs_token
    call fs_resolve_with_cwd
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_is_directory_marker
    cmp ax, 1
    je .rm_dir_hint
    mov di, fs_token
    call fs_remove_by_name
    cmp ax, 1
    je .done

    mov bl, COLOR_ERROR
    mov si, msg_file_not_found
    call print_color_string
    jmp .done

.mkdir:
    add si, 5
    call skip_spaces
    cmp byte [si], 0
    je .mkdir_usage
    mov di, dir_token
    mov cx, FS_NAME_MAX - 1
    call copy_token_limited
    call skip_spaces
    cmp byte [si], 0
    jne .mkdir_usage
    mov si, dir_token
    call fs_dir_create
    cmp ax, 1
    je .mkdir_ok
    cmp ax, 2
    je .mkdir_exists
    cmp ax, 3
    je .mkdir_invalid
    mov bl, COLOR_ERROR
    mov si, msg_fs_full
    call print_color_string
    jmp .done

.mkdir_ok:
    mov bl, COLOR_INFO
    mov si, msg_mkdir_ok_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, dir_token
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    call fs_store_save
    jmp .done

.mkdir_exists:
    mov bl, COLOR_WARN
    mov si, msg_mkdir_exists_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, dir_token
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.mkdir_invalid:
    mov bl, COLOR_WARN
    mov si, msg_mkdir_invalid
    call print_color_string
    jmp .done

.rmdir:
    add si, 5
    call skip_spaces
    cmp byte [si], 0
    je .rmdir_usage
    mov di, dir_token
    mov cx, FS_NAME_MAX - 1
    call copy_token_limited
    call skip_spaces
    cmp byte [si], 0
    jne .rmdir_usage
    mov si, dir_token
    call fs_dir_remove
    cmp ax, 1
    je .rmdir_ok
    cmp ax, 2
    je .rmdir_not_found
    cmp ax, 3
    je .rmdir_not_empty
    mov bl, COLOR_WARN
    mov si, msg_mkdir_invalid
    call print_color_string
    jmp .done

.rmdir_ok:
    mov bl, COLOR_INFO
    mov si, msg_rmdir_ok_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, dir_token
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    call fs_store_save
    jmp .done

.rmdir_not_found:
    mov bl, COLOR_ERROR
    mov si, msg_rmdir_not_found_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, dir_token
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.rmdir_not_empty:
    mov bl, COLOR_WARN
    mov si, msg_rmdir_not_empty_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, dir_token
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.touch:
    cmp byte [si + 1], 'k'
    je .touch_short
    add si, 5
    jmp .touch_parse
.touch_short:
    add si, 2
.touch_parse:
    call skip_spaces
    cmp byte [si], 0
    je .touch_usage

    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited

    mov si, fs_token
    call fs_resolve_with_cwd
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_validate_file_path
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_parent_ready_for_file
    cmp ax, 1
    jne .dir_missing

    mov si, fs_token
    mov di, fs_name_readme
    call strcmp
    cmp ax, 1
    je .touch_exists
    mov si, fs_token
    mov di, fs_name_judges
    call strcmp
    cmp ax, 1
    je .touch_exists
    mov si, fs_token
    mov di, fs_name_user
    call strcmp
    cmp ax, 1
    je .touch_exists
    mov si, fs_token
    mov di, fs_name_notes
    call strcmp
    cmp ax, 1
    je .touch_exists
    mov si, fs_token
    mov di, fs_name_cscript
    call strcmp
    cmp ax, 1
    je .touch_exists
    mov si, fs_token
    mov di, fs_name_custom_yaml
    call strcmp
    cmp ax, 1
    je .touch_exists

    mov si, fs_token
    call fs_user_create
    cmp ax, 1
    je .touch_ok
    cmp ax, 2
    je .touch_exists

    mov bl, COLOR_ERROR
    mov si, msg_fs_full
    call print_color_string
    jmp .done

.touch_ok:
    mov bl, COLOR_INFO
    mov si, msg_touch_ok_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, fs_token
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    call fs_store_save
    jmp .done

.touch_exists:
    mov bl, COLOR_WARN
    mov si, msg_touch_exists_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, fs_token
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    jmp .done

.cat:
    add si, 3
    call skip_spaces
    cmp byte [si], 0
    je .cat_usage

    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited
    mov si, fs_token
    call fs_resolve_with_cwd
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_validate_cat_path
    cmp ax, 1
    jne .path_invalid

    mov si, fs_token
    call fs_cat_by_name
    cmp ax, 1
    je .done

    mov bl, COLOR_ERROR
    mov si, msg_file_not_found
    call print_color_string
    jmp .done

.nano:
    add si, 4
    call skip_spaces
    cmp byte [si], 0
    je .nano_usage

    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_token_limited
    call skip_spaces
    cmp byte [si], 0
    jne .nano_usage

    mov si, fs_token
    call fs_resolve_with_cwd
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_validate_file_path
    cmp ax, 1
    jne .path_invalid
    mov si, fs_token
    call fs_parent_ready_for_file
    cmp ax, 1
    jne .dir_missing

    call clear_screen
    mov bl, COLOR_ACCENT
    mov si, msg_nano_title
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, fs_token
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string

    mov byte [nano_buffer], 0
    mov word [nano_line_count], 0
    mov si, fs_token
    mov di, nano_buffer
    call fs_copy_by_name
    cmp ax, 1
    jne .nano_new_file
    mov si, nano_buffer
    call count_lines_in_text
    mov [nano_line_count], ax
    mov bl, COLOR_INFO
    mov si, msg_nano_existing
    call print_color_string
    jmp .nano_edit_prompt

.nano_new_file:
    mov bl, COLOR_WARN
    mov si, msg_nano_new_file
    call print_color_string

.nano_edit_prompt:
    mov bl, COLOR_INFO
    mov si, msg_nano_prompt_1
    call print_color_string
    mov si, msg_nano_prompt_2
    call print_color_string

.nano_loop:
    mov bl, COLOR_PROMPT
    mov si, msg_nano_line_prompt
    call print_color_string
    mov di, input_buffer
    mov word [input_limit], MAX_INPUT
    call read_line_limited

    mov si, input_buffer
    mov di, cmd_nano_save
    call strcmp
    cmp ax, 1
    je .nano_save

    mov si, input_buffer
    mov di, cmd_nano_write
    call strcmp
    cmp ax, 1
    je .nano_write

    mov si, input_buffer
    mov di, cmd_nano_help
    call strcmp
    cmp ax, 1
    je .nano_help

    mov si, input_buffer
    mov di, cmd_nano_quit
    call strcmp
    cmp ax, 1
    je .nano_cancel

    cmp word [nano_line_count], NANO_MAX_LINES
    jae .nano_line_limit

    mov si, input_buffer
    mov di, nano_buffer
    call append_line_limited
    cmp ax, 1
    jne .nano_size_limit
    inc word [nano_line_count]
    jmp .nano_loop

.nano_save:
    mov si, nano_buffer
    mov di, fs_token
    call fs_write_by_name
    cmp ax, 1
    je .done
    cmp ax, 2
    je .fs_full

    mov bl, COLOR_ERROR
    mov si, msg_file_not_found
    call print_color_string
    jmp .done

.nano_write:
    mov si, nano_buffer
    mov di, fs_token
    call fs_write_by_name
    cmp ax, 1
    je .nano_write_ok
    cmp ax, 2
    je .fs_full
    mov bl, COLOR_ERROR
    mov si, msg_file_not_found
    call print_color_string
    jmp .nano_loop
.nano_write_ok:
    mov bl, COLOR_INFO
    mov si, msg_nano_written
    call print_color_string
    jmp .nano_loop

.nano_help:
    mov bl, COLOR_INFO
    mov si, msg_nano_prompt_3
    call print_color_string
    jmp .nano_loop

.nano_line_limit:
    mov bl, COLOR_WARN
    mov si, msg_nano_line_limit
    call print_color_string
    jmp .nano_loop

.nano_size_limit:
    mov bl, COLOR_WARN
    mov si, msg_nano_size_limit
    call print_color_string
    jmp .nano_loop

.nano_cancel:
    mov bl, COLOR_WARN
    mov si, msg_nano_cancel
    call print_color_string
    jmp .done

.rm_dir_hint:
    mov bl, COLOR_WARN
    mov si, msg_rm_dir_hint
    call print_color_string
    jmp .done

.cat_usage:
    mov bl, COLOR_WARN
    mov si, msg_cat_usage
    call print_color_string
    jmp .done

.nano_usage:
    mov bl, COLOR_WARN
    mov si, msg_nano_usage
    call print_color_string
    jmp .done

.fswrite_usage:
    mov bl, COLOR_WARN
    mov si, msg_fswrite_usage
    call print_color_string
    jmp .done

.append_usage:
    mov bl, COLOR_WARN
    mov si, msg_append_usage
    call print_color_string
    jmp .done

.rm_usage:
    mov bl, COLOR_WARN
    mov si, msg_rm_usage
    call print_color_string
    jmp .done

.touch_usage:
    mov bl, COLOR_WARN
    mov si, msg_touch_usage
    call print_color_string
    jmp .done

.mkdir_usage:
    mov bl, COLOR_WARN
    mov si, msg_mkdir_usage
    call print_color_string
    jmp .done

.rmdir_usage:
    mov bl, COLOR_WARN
    mov si, msg_rmdir_usage
    call print_color_string
    jmp .done

.path_invalid:
    mov bl, COLOR_WARN
    mov si, msg_path_invalid
    call print_color_string
    jmp .done

.dir_missing:
    mov bl, COLOR_ERROR
    mov si, msg_dir_missing
    call print_color_string
    jmp .done

.fs_full:
    mov bl, COLOR_ERROR
    mov si, msg_fs_full
    call print_color_string

.done:
    ret

show_banner:
    cmp byte [cfg_banner_enabled], 1
    jne .done

    mov bl, [cfg_color_frame]
    mov si, banner_top
    call print_color_string

    mov bl, COLOR_BANNER_1
    mov si, art_line_1
    call print_color_string
    mov bl, COLOR_BANNER_2
    mov si, art_line_2
    call print_color_string
    mov bl, COLOR_BANNER_3
    mov si, art_line_3
    call print_color_string
    mov bl, COLOR_BANNER_4
    mov si, art_line_4
    call print_color_string
    mov bl, COLOR_BANNER_5
    mov si, art_line_5
    call print_color_string
    mov bl, COLOR_BANNER_6
    mov si, art_line_6
    call print_color_string
    mov bl, [cfg_color_frame]
    mov si, banner_bottom
    call print_color_string

    mov bl, COLOR_BANNER_2
    mov si, fs_tagline
    call print_color_string

.done:
    ret

show_setup_wizard:
    mov bl, [cfg_color_frame]
    mov si, msg_setup_top
    call print_color_string
    mov bl, [cfg_color_ascii]
    mov si, msg_setup_title
    call print_color_string
    mov bl, [cfg_color_frame]
    mov si, msg_setup_sep
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_setup_line_1
    call print_color_string
    mov si, msg_setup_line_2
    call print_color_string
    mov bl, [cfg_color_frame]
    mov si, msg_setup_bottom
    call print_color_string
    ret

first_boot_setup:
    mov byte [setup_touched], 0
    cmp byte [user_initialized], 1
    jne .needs_setup
    cmp byte [region_initialized], 1
    jne .needs_setup
    cmp byte [password_initialized], 1
    jne .needs_setup
    jmp .done

.needs_setup:
    call clear_screen
    call show_setup_wizard
    cmp byte [user_initialized], 1
    je .check_region

    mov bl, COLOR_BANNER_2
    mov si, msg_setup_step_user
    call print_color_string
    mov bl, COLOR_WARN
    mov si, msg_pick_name
    call print_color_string
    mov di, username
    mov word [input_limit], USER_MAX
    call read_line_limited
    cmp byte [username], 0
    jne .name_done
    mov si, default_user
    mov di, username
    call copy_string
.name_done:
    mov byte [user_initialized], 1
    mov byte [setup_touched], 1

.check_region:
    cmp byte [region_initialized], 1
    je .check_password
    mov bl, COLOR_BANNER_2
    mov si, msg_setup_step_region
    call print_color_string
    call region_setup_interactive

.check_password:
    cmp byte [password_initialized], 1
    je .finish
    mov bl, COLOR_BANNER_2
    mov si, msg_setup_step_pass
    call print_color_string
    call password_setup_interactive

.finish:
    cmp byte [setup_touched], 1
    jne .done
    mov bl, COLOR_INFO
    mov si, msg_hello_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    cmp byte [username], 0
    jne .hello_name
    mov si, default_user
    call print_color_string
    jmp .hello_tail
.hello_name:
    mov si, username
    call print_color_string
.hello_tail:
    mov bl, COLOR_INFO
    mov si, msg_hello_suffix
    call print_color_string
    call fs_store_save
    mov bl, [cfg_color_frame]
    mov si, msg_setup_done
    call print_color_string
    call clear_screen
    call show_banner
    mov bl, COLOR_TITLE
    mov si, boot_msg
    call print_color_string

.done:
    ret

show_boot_notice:
    mov bl, [cfg_color_info]
    mov si, msg_boot_notice_line_1
    call print_color_string
    mov bl, COLOR_BANNER_5
    mov si, msg_boot_notice_line_2
    call print_color_string
    ret

region_setup_interactive:
    mov bl, COLOR_WARN
    mov si, msg_pick_region_title
    call print_color_string
    mov bl, COLOR_INFO
    mov si, msg_region_opt_1
    call print_color_string
    mov si, msg_region_opt_2
    call print_color_string
    mov si, msg_region_opt_3
    call print_color_string
    mov si, msg_region_opt_4
    call print_color_string
    mov si, msg_region_opt_5
    call print_color_string
    mov si, msg_region_opt_6
    call print_color_string
    mov si, msg_region_opt_7
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, msg_pick_region_choice
    call print_color_string
    mov di, input_buffer
    mov word [input_limit], 1
    call read_line_limited
    mov al, [input_buffer]
    cmp al, '1'
    je .set_pacific
    cmp al, '2'
    je .set_eastern
    cmp al, '3'
    je .set_utc
    cmp al, '4'
    je .set_cet
    cmp al, '5'
    je .set_moscow
    cmp al, '6'
    je .set_sg
    cmp al, '7'
    je .set_tokyo
    jmp .set_utc

.set_pacific:
    mov byte [timezone_offset], -8
    mov si, region_name_pacific
    jmp .store
.set_eastern:
    mov byte [timezone_offset], -5
    mov si, region_name_eastern
    jmp .store
.set_utc:
    mov byte [timezone_offset], 0
    mov si, region_name_utc
    jmp .store
.set_cet:
    mov byte [timezone_offset], 1
    mov si, region_name_cet
    jmp .store
.set_moscow:
    mov byte [timezone_offset], 3
    mov si, region_name_moscow
    jmp .store
.set_sg:
    mov byte [timezone_offset], 8
    mov si, region_name_sg
    jmp .store
.set_tokyo:
    mov byte [timezone_offset], 9
    mov si, region_name_tokyo

.store:
    mov di, region_name
    mov cx, REGION_MAX
    call copy_string_limited
    mov byte [region_initialized], 1
    mov byte [setup_touched], 1
    mov bl, COLOR_INFO
    mov si, msg_region_set_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, region_name
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    ret

password_setup_interactive:
    mov bl, COLOR_WARN
    mov si, msg_pick_pass
    call print_color_string
    mov di, password_plain
    mov word [input_limit], PASS_MAX
    call read_secret_limited
    cmp byte [password_plain], 0
    jne .set
    mov si, default_password
    mov di, password_plain
    mov cx, PASS_MAX
    call copy_string_limited
.set:
    mov si, password_plain
    call encrypt_password_to_store
    mov byte [password_initialized], 1
    mov byte [setup_touched], 1
    mov bl, COLOR_INFO
    mov si, msg_pass_set
    call print_color_string
    ret

show_region:
    mov bl, COLOR_ACCENT
    mov si, msg_region_current_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    cmp byte [region_initialized], 1
    je .region_named
    mov si, region_name_utc
    call print_color_string
    jmp .offset
.region_named:
    mov si, region_name
    call print_color_string
.offset:
    mov bl, COLOR_INFO
    mov si, msg_region_offset_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov al, [timezone_offset]
    call print_utc_offset
    mov bl, COLOR_INFO
    mov si, msg_region_offset_suffix
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    ret

show_prompt:
    mov bl, [cfg_color_prompt]
    cmp byte [username], 0
    jne .named
    mov si, default_user
    call print_color_string
    jmp .path

.named:
    mov si, username
    call print_color_string

.path:
    mov bl, [cfg_color_accent]
    mov al, ':'
    call putc_color
    mov al, '/'
    call putc_color
    cmp byte [current_dir], 0
    je .tail
    mov si, current_dir
    call print_color_string

.tail:
    mov bl, [cfg_color_prompt]
    cmp byte [cfg_prompt_compact], 1
    jne .classic
    mov si, prompt_tail_compact
    call print_color_string
    ret

.classic:
    mov si, prompt_tail
    call print_color_string
    ret

fs_list:
    mov bl, COLOR_BANNER_2
    mov si, msg_fs_title
    call print_color_string
    mov bl, COLOR_FRAME
    mov si, msg_fs_legend
    call print_color_string
    mov bl, COLOR_INFO
    mov si, fs_entry_readme
    call print_color_string
    mov bl, COLOR_WARN
    mov si, fs_entry_judges
    call print_color_string
    mov bl, COLOR_PROMPT
    mov si, fs_entry_user
    call print_color_string
    mov bl, COLOR_ACCENT
    mov si, fs_entry_notes
    call print_color_string
    ; OATB_PATCH_FS_LIST
    call fs_list_user_files
    ret

fs_info:
    mov bl, COLOR_BANNER_2
    mov si, msg_fsinfo_title
    call print_color_string
    mov bl, COLOR_INFO
    mov si, msg_fsinfo_line_1
    call print_color_string
    mov si, msg_fsinfo_line_2
    call print_color_string
    mov bl, COLOR_WARN
    mov si, msg_fsinfo_line_3
    call print_color_string
    ret

fs_cat_by_name:
    mov di, fs_name_readme
    call strcmp
    cmp ax, 1
    je .readme

    mov di, fs_name_judges
    call strcmp
    cmp ax, 1
    je .judges

    mov di, fs_name_user
    call strcmp
    cmp ax, 1
    je .user

    mov di, fs_name_notes
    call strcmp
    cmp ax, 1
    je .notes

    ; OATB_PATCH_FS_CAT
    call fs_user_find_by_name
    cmp ax, 1
    jne .not_found
    mov bl, COLOR_ACCENT
    mov si, di
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    mov ax, 1
    ret

.not_found:
    xor ax, ax
    ret

.readme:
    mov bl, COLOR_INFO
    mov si, fs_readme
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    mov ax, 1
    ret

.judges:
    mov bl, COLOR_WARN
    mov si, fs_judges
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    mov ax, 1
    ret

.user:
    mov bl, COLOR_BANNER_2
    mov si, msg_userfile_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    cmp byte [username], 0
    jne .show_saved_name
    mov si, default_user
    call print_color_string
    jmp .tail

.show_saved_name:
    mov si, username
    call print_color_string

.tail:
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    mov ax, 1
    ret

.notes:
    mov bl, COLOR_ACCENT
    mov si, fs_notes
    call print_color_string
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    mov ax, 1
    ret

fs_write_by_name:
    mov bx, si
    mov si, di
    mov di, fs_name_readme
    call strcmp
    cmp ax, 1
    je .write_readme

    mov si, fs_token
    mov di, fs_name_judges
    call strcmp
    cmp ax, 1
    je .write_judges

    mov si, fs_token
    mov di, fs_name_user
    call strcmp
    cmp ax, 1
    je .write_user

    mov si, fs_token
    mov di, fs_name_notes
    call strcmp
    cmp ax, 1
    je .write_notes

    mov si, fs_token
    call fs_user_find_by_name
    cmp ax, 1
    je .write_custom
    mov si, fs_token
    call fs_user_create
    cmp ax, 1
    jne .write_no_slot

.write_custom:
    mov si, bx
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov bl, COLOR_INFO
    mov si, msg_fswrite_ok
    call print_color_string
    call fs_store_save
    mov ax, 1
    ret

.write_no_slot:
    mov ax, 2
    ret

.write_readme:
    mov si, bx
    mov di, fs_readme
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov bl, COLOR_INFO
    mov si, msg_fswrite_ok
    call print_color_string
    call fs_store_save
    mov ax, 1
    ret

.write_judges:
    mov si, bx
    mov di, fs_judges
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov bl, COLOR_WARN
    mov si, msg_fswrite_ok
    call print_color_string
    call fs_store_save
    mov ax, 1
    ret

.write_user:
    mov si, bx
    mov di, username
    mov cx, USER_MAX
    call copy_string_limited
    mov byte [user_initialized], 1
    mov bl, COLOR_INFO
    mov si, msg_fswrite_user_ok
    call print_color_string
    call fs_store_save
    mov ax, 1
    ret

.write_notes:
    mov si, bx
    mov di, fs_notes
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov bl, COLOR_ACCENT
    mov si, msg_fswrite_ok
    call print_color_string
    call fs_store_save
    mov ax, 1
    ret

fs_append_by_name:
    mov bx, si
    mov si, di
    mov di, fs_name_readme
    call strcmp
    cmp ax, 1
    je .append_readme

    mov si, fs_token
    mov di, fs_name_judges
    call strcmp
    cmp ax, 1
    je .append_judges

    mov si, fs_token
    mov di, fs_name_notes
    call strcmp
    cmp ax, 1
    je .append_notes

    mov si, fs_token
    call fs_user_find_by_name
    cmp ax, 1
    je .append_custom
    mov si, fs_token
    call fs_user_create
    cmp ax, 1
    jne .append_no_slot
.append_custom:
    jmp .append_to_target

.append_no_slot:
    mov ax, 2
    ret

.append_readme:
    mov di, fs_readme
    jmp .append_to_target

.append_judges:
    mov di, fs_judges
    jmp .append_to_target

.append_notes:
    mov di, fs_notes

.append_to_target:
    mov dx, di
    mov cx, FS_TEXT_MAX
.seek_end:
    cmp cx, 0
    je .append_done
    cmp byte [di], 0
    je .append_space
    inc di
    dec cx
    jmp .seek_end

.append_space:
    cmp di, dx
    je .append_copy

    cmp cx, 0
    je .append_done
    mov byte [di], ' '
    inc di
    dec cx
    je .append_done

.append_copy:
    mov si, bx
    call copy_string_limited
.append_done:
    mov bl, COLOR_INFO
    mov si, msg_append_ok
    call print_color_string
    call fs_store_save
    mov ax, 1
    ret

fs_remove_by_name:
    mov si, di
    mov di, fs_name_readme
    call strcmp
    cmp ax, 1
    je .rm_readme

    mov si, fs_token
    mov di, fs_name_judges
    call strcmp
    cmp ax, 1
    je .rm_judges

    mov si, fs_token
    mov di, fs_name_user
    call strcmp
    cmp ax, 1
    je .rm_user

    mov si, fs_token
    mov di, fs_name_notes
    call strcmp
    cmp ax, 1
    je .rm_notes

    mov si, fs_token
    call fs_user_remove_by_name
    cmp ax, 1
    je .rm_ok

    xor ax, ax
    ret

.rm_readme:
    mov byte [fs_readme], 0
    jmp .rm_ok

.rm_judges:
    mov byte [fs_judges], 0
    jmp .rm_ok

.rm_user:
    mov byte [username], 0
    mov byte [user_initialized], 0
    jmp .rm_ok

.rm_notes:
    mov byte [fs_notes], 0

.rm_ok:
    mov bl, COLOR_WARN
    mov si, msg_rm_ok
    call print_color_string
    call fs_store_save
    mov ax, 1
    ret

fs_list_user_files:
    mov si, ufs1_name
    call fs_list_user_entry
    mov si, ufs2_name
    call fs_list_user_entry
    mov si, ufs3_name
    call fs_list_user_entry
    mov si, ufs4_name
    call fs_list_user_entry
    mov si, ufs5_name
    call fs_list_user_entry
    mov si, ufs6_name
    call fs_list_user_entry
    ret

fs_list_user_entry:
    cmp byte [si], 0
    je .done
    push si
    call fs_is_directory_marker
    cmp ax, 1
    pop si
    jne .entry_file
    mov bl, COLOR_BANNER_5
    push si
    mov si, msg_fs_dir_prefix
    call print_color_string
    pop si
    call print_dir_name_clean
    jmp .entry_tail
.entry_file:
    mov bl, COLOR_PROMPT
    push si
    mov si, msg_fs_file_prefix
    call print_color_string
    pop si
    call print_color_string
.entry_tail:
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
.done:
    ret

print_dir_name_clean:
.loop:
    mov al, [si]
    cmp al, 0
    je .done
    cmp al, '/'
    jne .emit
    cmp byte [si + 1], 0
    je .done
.emit:
    call putc_color
    inc si
    jmp .loop
.done:
    ret

fs_user_find_by_name:
    mov di, ufs1_name
    call strcmp
    cmp ax, 1
    je .slot1
    mov di, ufs2_name
    call strcmp
    cmp ax, 1
    je .slot2
    mov di, ufs3_name
    call strcmp
    cmp ax, 1
    je .slot3
    mov di, ufs4_name
    call strcmp
    cmp ax, 1
    je .slot4
    mov di, ufs5_name
    call strcmp
    cmp ax, 1
    je .slot5
    mov di, ufs6_name
    call strcmp
    cmp ax, 1
    je .slot6
    xor ax, ax
    ret
.slot1:
    mov di, ufs1_data
    mov ax, 1
    ret
.slot2:
    mov di, ufs2_data
    mov ax, 1
    ret
.slot3:
    mov di, ufs3_data
    mov ax, 1
    ret
.slot4:
    mov di, ufs4_data
    mov ax, 1
    ret
.slot5:
    mov di, ufs5_data
    mov ax, 1
    ret
.slot6:
    mov di, ufs6_data
    mov ax, 1
    ret

fs_user_find_free_slot:
    cmp byte [ufs1_name], 0
    je .slot1
    cmp byte [ufs2_name], 0
    je .slot2
    cmp byte [ufs3_name], 0
    je .slot3
    cmp byte [ufs4_name], 0
    je .slot4
    cmp byte [ufs5_name], 0
    je .slot5
    cmp byte [ufs6_name], 0
    je .slot6
    xor ax, ax
    ret
.slot1:
    mov bx, ufs1_name
    mov di, ufs1_data
    mov ax, 1
    ret
.slot2:
    mov bx, ufs2_name
    mov di, ufs2_data
    mov ax, 1
    ret
.slot3:
    mov bx, ufs3_name
    mov di, ufs3_data
    mov ax, 1
    ret
.slot4:
    mov bx, ufs4_name
    mov di, ufs4_data
    mov ax, 1
    ret
.slot5:
    mov bx, ufs5_name
    mov di, ufs5_data
    mov ax, 1
    ret
.slot6:
    mov bx, ufs6_name
    mov di, ufs6_data
    mov ax, 1
    ret

fs_user_create:
    call fs_user_find_by_name
    cmp ax, 1
    jne .create_new
    mov ax, 2
    ret
.create_new:
    call fs_user_find_free_slot
    cmp ax, 1
    jne .full
    push di
    mov di, bx
    mov cx, FS_NAME_MAX
    call copy_string_limited
    pop di
    mov byte [di], 0
    mov ax, 1
    ret
.full:
    xor ax, ax
    ret

fs_user_remove_by_name:
    mov di, ufs1_name
    call strcmp
    cmp ax, 1
    je .slot1
    mov di, ufs2_name
    call strcmp
    cmp ax, 1
    je .slot2
    mov di, ufs3_name
    call strcmp
    cmp ax, 1
    je .slot3
    mov di, ufs4_name
    call strcmp
    cmp ax, 1
    je .slot4
    mov di, ufs5_name
    call strcmp
    cmp ax, 1
    je .slot5
    mov di, ufs6_name
    call strcmp
    cmp ax, 1
    je .slot6
    xor ax, ax
    ret
.slot1:
    mov byte [ufs1_name], 0
    mov byte [ufs1_data], 0
    mov ax, 1
    ret
.slot2:
    mov byte [ufs2_name], 0
    mov byte [ufs2_data], 0
    mov ax, 1
    ret
.slot3:
    mov byte [ufs3_name], 0
    mov byte [ufs3_data], 0
    mov ax, 1
    ret
.slot4:
    mov byte [ufs4_name], 0
    mov byte [ufs4_data], 0
    mov ax, 1
    ret
.slot5:
    mov byte [ufs5_name], 0
    mov byte [ufs5_data], 0
    mov ax, 1
    ret
.slot6:
    mov byte [ufs6_name], 0
    mov byte [ufs6_data], 0
    mov ax, 1
    ret

fs_validate_dir_name:
    cmp byte [si], 0
    je .no
    cmp byte [si], '/'
    je .no
.loop:
    mov al, [si]
    cmp al, 0
    je .yes
    cmp al, '/'
    je .no
    inc si
    jmp .loop
.yes:
    mov ax, 1
    ret
.no:
    xor ax, ax
    ret

fs_validate_file_path:
    cmp byte [si], 0
    je .no
    cmp byte [si], '/'
    je .no
    xor dx, dx
.loop:
    mov al, [si]
    cmp al, 0
    je .yes
    cmp al, '/'
    jne .next
    inc dl
    cmp dl, 1
    ja .no
    cmp byte [si + 1], 0
    je .no
.next:
    inc si
    jmp .loop
.yes:
    mov ax, 1
    ret
.no:
    xor ax, ax
    ret

fs_resolve_with_cwd:
    push bx
    push cx
    push di
    mov bx, si
    cmp byte [current_dir], 0
    je .copy_plain

    mov si, bx
.scan_path:
    mov al, [si]
    cmp al, 0
    je .merge
    cmp al, '/'
    je .copy_plain
    inc si
    jmp .scan_path

.merge:
    mov si, current_dir
    mov di, fs_token
    mov cx, FS_NAME_MAX - 1
    call copy_string_limited
    mov si, fs_token
    call string_length
    cmp ax, FS_NAME_MAX - 1
    jae .fail
    mov di, fs_token
    add di, ax
    mov byte [di], '/'
    inc di
    mov byte [di], 0
    mov cx, FS_NAME_MAX
    sub cx, ax
    sub cx, 2
    jb .fail
    mov si, bx
    call copy_string_limited
    mov si, fs_token
    mov ax, 1
    jmp .done

.copy_plain:
    mov si, bx
    mov di, fs_token
    mov cx, FS_NAME_MAX
    call copy_string_limited
    mov si, fs_token
    mov ax, 1
    jmp .done

.fail:
    xor ax, ax

.done:
    pop di
    pop cx
    pop bx
    ret

fs_validate_cat_path:
    push si
    call fs_validate_file_path
    cmp ax, 1
    jne .no
    pop si
    push si
    call fs_is_directory_marker
    cmp ax, 1
    je .no
    mov ax, 1
    pop si
    ret
.no:
    pop si
    xor ax, ax
    ret

fs_is_directory_marker:
    cmp byte [si], 0
    je .no
    cmp byte [si], '/'
    je .no
    xor dx, dx
.loop:
    mov al, [si]
    cmp al, 0
    je .no
    cmp al, '/'
    jne .next
    inc dl
    cmp dl, 1
    jne .no
    cmp byte [si + 1], 0
    jne .no
    mov ax, 1
    ret
.next:
    inc si
    jmp .loop
.no:
    xor ax, ax
    ret

fs_dir_build_marker:
    push si
    push di
    push cx
    mov di, dir_marker
    mov cx, FS_NAME_MAX - 1
    call copy_string_limited
    mov byte [di], '/'
    inc di
    mov byte [di], 0
    pop cx
    pop di
    pop si
    ret

fs_dir_exists:
    push si
    call fs_validate_dir_name
    cmp ax, 1
    jne .no
    pop si
    call fs_dir_build_marker
    mov si, dir_marker
    call fs_user_find_by_name
    cmp ax, 1
    jne .no_ret
    mov ax, 1
    ret
.no:
    pop si
.no_ret:
    xor ax, ax
    ret

fs_parent_ready_for_file:
    push bx
    push cx
    push di
    mov bx, si
.scan:
    mov al, [si]
    cmp al, 0
    je .root_ok
    cmp al, '/'
    je .have_dir
    inc si
    jmp .scan
.root_ok:
    mov ax, 1
    jmp .done
.have_dir:
    mov si, bx
    mov di, dir_token
    mov cx, FS_NAME_MAX - 1
.copy_dir:
    mov al, [si]
    cmp al, '/'
    je .copy_done
    cmp al, 0
    je .copy_fail
    mov [di], al
    inc di
    inc si
    dec cx
    jnz .copy_dir
    jmp .copy_fail
.copy_done:
    mov byte [di], 0
    mov si, dir_token
    call fs_dir_exists
    jmp .done
.copy_fail:
    xor ax, ax
.done:
    pop di
    pop cx
    pop bx
    ret

fs_dir_create:
    call fs_validate_dir_name
    cmp ax, 1
    jne .invalid
    call fs_dir_build_marker
    mov si, dir_marker
    call fs_user_create
    cmp ax, 1
    je .ok
    cmp ax, 2
    je .exists
    xor ax, ax
    ret
.invalid:
    mov ax, 3
    ret
.exists:
    mov ax, 2
    ret
.ok:
    mov ax, 1
    ret

fs_dir_remove:
    call fs_validate_dir_name
    cmp ax, 1
    jne .invalid
    call fs_dir_build_marker
    mov si, dir_marker
    call fs_user_find_by_name
    cmp ax, 1
    jne .not_found

    mov si, ufs1_name
    call .check_slot
    cmp ax, 1
    je .not_empty
    mov si, ufs2_name
    call .check_slot
    cmp ax, 1
    je .not_empty
    mov si, ufs3_name
    call .check_slot
    cmp ax, 1
    je .not_empty
    mov si, ufs4_name
    call .check_slot
    cmp ax, 1
    je .not_empty
    mov si, ufs5_name
    call .check_slot
    cmp ax, 1
    je .not_empty
    mov si, ufs6_name
    call .check_slot
    cmp ax, 1
    je .not_empty

    mov si, dir_marker
    call fs_user_remove_by_name
    cmp ax, 1
    jne .not_found
    mov ax, 1
    ret

.check_slot:
    cmp byte [si], 0
    je .slot_ok
    push si
    mov di, dir_marker
    call strprefix
    cmp ax, 1
    jne .slot_not_prefix
    pop si
    push si
    mov di, dir_marker
    call strcmp
    cmp ax, 1
    jne .slot_not_empty
    pop si
    xor ax, ax
    ret
.slot_not_prefix:
    pop si
.slot_ok:
    xor ax, ax
    ret
.slot_not_empty:
    pop si
    mov ax, 1
    ret

.invalid:
    xor ax, ax
    ret
.not_found:
    mov ax, 2
    ret
.not_empty:
    mov ax, 3
    ret

fs_copy_by_name:
    push bx
    mov bx, di
    mov di, fs_name_readme
    call strcmp
    cmp ax, 1
    je .copy_readme
    mov di, fs_name_judges
    call strcmp
    cmp ax, 1
    je .copy_judges
    mov di, fs_name_notes
    call strcmp
    cmp ax, 1
    je .copy_notes
    mov di, fs_name_user
    call strcmp
    cmp ax, 1
    je .copy_user
    call fs_user_find_by_name
    cmp ax, 1
    jne .not_found
    mov si, di
    jmp .copy
.copy_readme:
    mov si, fs_readme
    jmp .copy
.copy_judges:
    mov si, fs_judges
    jmp .copy
.copy_notes:
    mov si, fs_notes
    jmp .copy
.copy_user:
    mov si, username
.copy:
    mov di, bx
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov ax, 1
    pop bx
    ret
.not_found:
    xor ax, ax
    pop bx
    ret

count_user_files:
    xor bx, bx
    mov si, ufs1_name
    call .count_slot
    mov si, ufs2_name
    call .count_slot
    mov si, ufs3_name
    call .count_slot
    mov si, ufs4_name
    call .count_slot
    mov si, ufs5_name
    call .count_slot
    mov si, ufs6_name
    call .count_slot
    mov ax, bx
    ret
.count_slot:
    cmp byte [si], 0
    je .count_done
    push si
    call fs_is_directory_marker
    cmp ax, 1
    pop si
    je .count_done
    inc bx
.count_done:
    ret

count_user_dirs:
    xor bx, bx
    mov si, ufs1_name
    call .count_slot
    mov si, ufs2_name
    call .count_slot
    mov si, ufs3_name
    call .count_slot
    mov si, ufs4_name
    call .count_slot
    mov si, ufs5_name
    call .count_slot
    mov si, ufs6_name
    call .count_slot
    mov ax, bx
    ret
.count_slot:
    cmp byte [si], 0
    je .count_done
    push si
    call fs_is_directory_marker
    cmp ax, 1
    pop si
    jne .count_done
    inc bx
.count_done:
    ret

show_help:
    mov bl, [cfg_color_accent]
    mov si, msg_help_title
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_help_core
    call print_color_string
    mov bl, [cfg_color_ascii]
    mov si, msg_help_utils
    call print_color_string
    mov bl, [cfg_color_frame]
    mov si, msg_help_info
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_help_fs
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_help_atbman
    call print_color_string
    mov bl, [patch_state_retro_color]
    mov si, msg_help_patch_retro
    call print_color_string
    mov bl, [patch_state_hints_color]
    mov si, msg_help_patch_alias
    call print_color_string
    mov bl, [patch_state_hack_color]
    mov si, msg_help_patch_hack
    call print_color_string
    mov bl, [patch_state_customize_color]
    mov si, msg_help_patch_customize
    call print_color_string
    mov bl, [cfg_color_warn]
    mov si, msg_help_tip
    call print_color_string
    ret

show_about:
    mov bl, [cfg_color_ascii]
    mov si, about_top
    call print_color_string
    mov si, about_title
    call print_color_string
    mov si, about_sep
    call print_color_string

    mov bl, [cfg_color_info]
    mov si, about_line_1
    call print_color_string
    mov bl, [cfg_color_frame]
    mov si, about_line_2
    call print_color_string
    mov bl, [cfg_color_ascii]
    mov si, about_line_3
    call print_color_string

    mov bl, [cfg_color_accent]
    mov si, about_user_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    cmp byte [username], 0
    jne .name
    mov si, default_user
    call print_color_string
    jmp .user_tail

.name:
    mov si, username
    call print_color_string

.user_tail:
    mov bl, [cfg_color_ascii]
    mov si, about_user_suffix
    call print_color_string
    mov si, about_bottom
    call print_color_string
    ret

show_patches:
    mov bl, [cfg_color_frame]
    mov si, msg_patches_title
    call print_color_string
    mov bl, [patch_state_retro_color]
    mov si, msg_patch_state_retro
    call print_color_string
    mov bl, [patch_state_hints_color]
    mov si, msg_patch_state_hints
    call print_color_string
    mov bl, [patch_state_hack_color]
    mov si, msg_patch_state_hack
    call print_color_string
    mov bl, [patch_state_customize_color]
    mov si, msg_patch_state_customize
    call print_color_string
    ret

show_patches_raw:
    mov bl, [cfg_color_frame]
    mov si, msg_patches_raw_title
    call print_color_string

    mov bl, COLOR_INFO
    mov si, msg_patch_raw_retro
    call print_color_string
    mov bl, COLOR_PROMPT
    mov al, [patch_state_retro_color]
    cmp al, COLOR_PROMPT
    jne .retro_off
    mov al, '1'
    jmp .retro_emit
.retro_off:
    mov al, '0'
.retro_emit:
    call putc_color
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string

    mov bl, COLOR_INFO
    mov si, msg_patch_raw_hints
    call print_color_string
    mov bl, COLOR_PROMPT
    mov al, [patch_state_hints_color]
    cmp al, COLOR_PROMPT
    jne .hints_off
    mov al, '1'
    jmp .hints_emit
.hints_off:
    mov al, '0'
.hints_emit:
    call putc_color
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string

    mov bl, COLOR_INFO
    mov si, msg_patch_raw_hack
    call print_color_string
    mov bl, COLOR_PROMPT
    mov al, [patch_state_hack_color]
    cmp al, COLOR_PROMPT
    jne .hack_off
    mov al, '1'
    jmp .hack_emit
.hack_off:
    mov al, '0'
.hack_emit:
    call putc_color
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string

    mov bl, COLOR_INFO
    mov si, msg_patch_raw_customize
    call print_color_string
    mov bl, COLOR_PROMPT
    mov al, [patch_state_customize_color]
    cmp al, COLOR_PROMPT
    jne .customize_off
    mov al, '1'
    jmp .customize_emit
.customize_off:
    mov al, '0'
.customize_emit:
    call putc_color
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    ret

show_uptime:
    mov bl, COLOR_ACCENT
    mov si, msg_uptime_prefix
    call print_color_string
    call get_elapsed_ticks
    mov bx, 1092
    div bx
    mov bl, COLOR_PROMPT
    call print_u16
    mov bl, COLOR_DEFAULT
    mov si, msg_uptime_suffix
    call print_color_string
    ret

show_time:
    mov ah, 0x02
    int 0x1A
    jc .read_fail
    mov al, ch
    call bcd_to_bin8
    add al, [timezone_offset]
.normalize_low:
    cmp al, 0
    jge .normalize_high
    add al, 24
    jmp .normalize_low
.normalize_high:
    cmp al, 24
    jb .emit
    sub al, 24
    jmp .normalize_high
.emit:
    mov [time_hour], al
    mov al, cl
    call bcd_to_bin8
    mov [time_min], al
    mov al, dh
    call bcd_to_bin8
    mov [time_sec], al
    mov bl, COLOR_ACCENT
    mov si, msg_time_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov al, [time_hour]
    call print_two_digits
    mov al, ':'
    call putc_color
    mov al, [time_min]
    call print_two_digits
    mov al, ':'
    call putc_color
    mov al, [time_sec]
    call print_two_digits
    mov bl, COLOR_INFO
    mov si, msg_fetch_tz
    call print_color_string
    mov bl, COLOR_PROMPT
    mov al, [timezone_offset]
    call print_utc_offset
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    ret
.read_fail:
    mov bl, COLOR_ERROR
    mov si, msg_rtc_fail
    call print_color_string
    ret

show_date:
    mov ah, 0x04
    int 0x1A
    jc .read_fail
    mov bl, COLOR_ACCENT
    mov si, msg_date_prefix
    call print_color_string
    mov bl, COLOR_PROMPT
    mov al, dl
    call print_bcd_byte
    mov al, '.'
    call putc_color
    mov al, dh
    call print_bcd_byte
    mov al, '.'
    call putc_color
    mov al, ch
    call print_bcd_byte
    mov al, cl
    call print_bcd_byte
    mov bl, COLOR_DEFAULT
    mov si, msg_newline
    call print_color_string
    ret
.read_fail:
    mov bl, COLOR_ERROR
    mov si, msg_rtc_fail
    call print_color_string
    ret

show_version:
    mov bl, COLOR_BANNER_1
    mov si, msg_version
    call print_color_string
    ret

show_fetch:
    mov bl, [cfg_color_frame]
    mov si, msg_fetch_head
    call print_color_string
    mov bl, [cfg_color_ascii]
    mov si, msg_fetch_logo_1
    call print_color_string
    mov si, msg_fetch_logo_2
    call print_color_string
    mov si, msg_fetch_logo_3
    call print_color_string

    mov bl, [cfg_color_info]
    mov si, msg_fetch_product
    call print_color_string
    mov bl, [cfg_color_info]
    mov si, msg_fetch_component_1
    call print_color_string
    mov bl, [cfg_color_warn]
    mov si, msg_fetch_component_2
    call print_color_string
    mov bl, [cfg_color_accent]
    mov si, msg_fetch_component_3
    call print_color_string

    mov bl, [cfg_color_info]
    mov si, msg_fetch_user
    call print_color_string
    mov bl, [cfg_color_prompt]
    cmp byte [username], 0
    jne .fetch_user_named
    mov si, default_user
    call print_color_string
    jmp .fetch_user_done
.fetch_user_named:
    mov si, username
    call print_color_string
.fetch_user_done:
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string

    mov bl, [cfg_color_info]
    mov si, msg_fetch_cwd
    call print_color_string
    mov bl, [cfg_color_prompt]
    cmp byte [current_dir], 0
    jne .fetch_cwd_named
    mov si, arg_root
    call print_color_string
    jmp .fetch_cwd_done
.fetch_cwd_named:
    mov al, '/'
    call putc_color
    mov si, current_dir
    call print_color_string
.fetch_cwd_done:
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string

    mov bl, [cfg_color_info]
    mov si, msg_fetch_region
    call print_color_string
    mov bl, [cfg_color_prompt]
    cmp byte [region_initialized], 1
    je .fetch_region_named
    mov si, region_name_utc
    call print_color_string
    jmp .fetch_region_offset
.fetch_region_named:
    mov si, region_name
    call print_color_string
.fetch_region_offset:
    mov bl, [cfg_color_info]
    mov si, msg_region_offset_prefix
    call print_color_string
    mov bl, [cfg_color_prompt]
    mov al, [timezone_offset]
    call print_utc_offset
    mov bl, [cfg_color_info]
    mov si, msg_region_offset_suffix
    call print_color_string
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string

    mov bl, [cfg_color_info]
    mov si, msg_fetch_uptime
    call print_color_string
    call get_elapsed_ticks
    mov bx, 1092
    div bx
    mov bl, [cfg_color_prompt]
    call print_u16
    mov bl, [cfg_color_info]
    mov si, msg_uptime_suffix
    call print_color_string

    mov bl, [cfg_color_info]
    mov si, msg_fetch_fs
    call print_color_string
    call count_user_dirs
    mov bl, [cfg_color_prompt]
    call print_u16
    mov bl, [cfg_color_info]
    mov si, msg_fetch_dirs_sep
    call print_color_string
    call count_user_files
    mov bl, [cfg_color_prompt]
    call print_u16
    mov bl, [cfg_color_info]
    mov si, msg_fetch_files_tail
    call print_color_string

    mov bl, [cfg_color_info]
    mov si, msg_fetch_auth
    call print_color_string
    mov bl, [cfg_color_prompt]
    cmp byte [password_initialized], 1
    je .fetch_auth_on
    mov si, msg_fetch_auth_off
    call print_color_string
    jmp .fetch_done
.fetch_auth_on:
    mov si, msg_fetch_auth_on
    call print_color_string
.fetch_done:
    mov bl, [cfg_color_default]
    mov si, msg_newline
    call print_color_string
    ret

init_boot_ticks:
    call get_bios_ticks
    mov [boot_ticks], ax
    mov [boot_ticks + 2], dx
    ret

init_openasm_fs:
    mov si, fs_readme_default
    mov di, fs_readme
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov si, fs_judges_default
    mov di, fs_judges
    mov cx, FS_TEXT_MAX
    call copy_string_limited
    mov byte [fs_notes], 0
    mov byte [ufs1_name], 0
    mov byte [ufs1_data], 0
    mov byte [ufs2_name], 0
    mov byte [ufs2_data], 0
    mov byte [ufs3_name], 0
    mov byte [ufs3_data], 0
    mov byte [ufs4_name], 0
    mov byte [ufs4_data], 0
    mov byte [ufs5_name], 0
    mov byte [ufs5_data], 0
    mov byte [ufs6_name], 0
    mov byte [ufs6_data], 0
    mov byte [region_initialized], 0
    mov byte [timezone_offset], 0
    mov si, region_name_utc
    mov di, region_name
    mov cx, REGION_MAX
    call copy_string_limited
    mov byte [password_initialized], 0
    mov byte [user_pass_enc], 0
    mov byte [current_dir], 0
    mov byte [setup_touched], 0
    mov byte [cscript_enabled], 0
    mov byte [atb_pkg1_name], 0
    mov byte [atb_pkg1_source], 0
    mov byte [atb_pkg1_runtime], 0
    mov byte [atb_pkg2_name], 0
    mov byte [atb_pkg2_source], 0
    mov byte [atb_pkg2_runtime], 0
    mov byte [atb_pkg3_name], 0
    mov byte [atb_pkg3_source], 0
    mov byte [atb_pkg3_runtime], 0
    mov byte [cfg_banner_enabled], 1
    mov byte [cfg_prompt_compact], 0
    mov byte [cfg_theme_index], 0
    mov byte [cfg_color_default], COLOR_DEFAULT
    mov byte [cfg_color_info], COLOR_INFO
    mov byte [cfg_color_warn], COLOR_WARN
    mov byte [cfg_color_error], COLOR_ERROR
    mov byte [cfg_color_prompt], COLOR_PROMPT
    mov byte [cfg_color_ascii], COLOR_ASCII
    mov byte [cfg_color_frame], COLOR_FRAME
    mov byte [cfg_color_accent], COLOR_ACCENT
    ret

init_runtime_strings:
    mov si, msg_unknown_default
    mov di, msg_unknown
    mov cx, 63
    call copy_string_limited
    ret

sanitize_runtime_state:
    cmp byte [msg_unknown], 0
    jne .check_default
    mov si, msg_unknown_default
    mov di, msg_unknown
    mov cx, 63
    call copy_string_limited

.check_default:
    cmp byte [cfg_color_default], 0
    jne .check_info
    mov byte [cfg_color_default], COLOR_DEFAULT
.check_info:
    cmp byte [cfg_color_info], 0
    jne .check_warn
    mov byte [cfg_color_info], COLOR_INFO
.check_warn:
    cmp byte [cfg_color_warn], 0
    jne .check_error
    mov byte [cfg_color_warn], COLOR_WARN
.check_error:
    cmp byte [cfg_color_error], 0
    jne .check_prompt
    mov byte [cfg_color_error], COLOR_ERROR
.check_prompt:
    cmp byte [cfg_color_prompt], 0
    jne .check_ascii
    mov byte [cfg_color_prompt], COLOR_PROMPT
.check_ascii:
    cmp byte [cfg_color_ascii], 0
    jne .check_frame
    mov byte [cfg_color_ascii], COLOR_ASCII
.check_frame:
    cmp byte [cfg_color_frame], 0
    jne .check_accent
    mov byte [cfg_color_frame], COLOR_FRAME
.check_accent:
    cmp byte [cfg_color_accent], 0
    jne .check_region
    mov byte [cfg_color_accent], COLOR_ACCENT
.check_region:
    cmp byte [region_initialized], 1
    je .check_region_name
    mov byte [timezone_offset], 0
    mov si, region_name_utc
    mov di, region_name
    mov cx, REGION_MAX
    call copy_string_limited
    jmp .check_tz
.check_region_name:
    cmp byte [region_name], 0
    jne .check_tz
    mov si, region_name_utc
    mov di, region_name
    mov cx, REGION_MAX
    call copy_string_limited
.check_tz:
    mov al, [timezone_offset]
    cmp al, -12
    jl .reset_tz
    cmp al, 14
    jg .reset_tz
    jmp .check_password
.reset_tz:
    mov byte [timezone_offset], 0
.check_password:
    cmp byte [password_initialized], 1
    jne .check_cwd
    cmp byte [user_pass_enc], 0
    jne .check_cwd
    mov byte [password_initialized], 0
.check_cwd:
    cmp byte [current_dir], 0
    je .done
    mov si, current_dir
    call fs_dir_exists
    cmp ax, 1
    je .done
    mov byte [current_dir], 0
.done:
    ret

fs_store_load:
    push ds
    push es

    mov ax, FS_STORE_SEG
    mov es, ax
    mov ax, FS_STORE_LBA
    mov bx, FS_STORE_BUFFER
    mov cx, FS_STORE_SECTORS
    call disk_read_lba_multi
    jc .init_store

    mov ax, FS_STORE_SEG
    mov ds, ax
    mov ax, cs
    mov es, ax

    mov si, FS_STORE_BUFFER
    mov di, fs_store_magic
    mov cx, 8
    call mem_equal_n
    cmp ax, 1
    jne .init_store

    mov si, FS_STORE_BUFFER + 8
    lodsb
    mov [user_initialized], al

    mov di, username
    mov cx, USER_MAX + 1
    call mem_copy_n

    mov di, msg_unknown
    mov cx, 64
    call mem_copy_n

    mov di, fs_readme
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n

    mov di, fs_judges
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n

    mov di, fs_notes
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n

    mov di, ufs1_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov di, ufs1_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov di, ufs2_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov di, ufs2_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov di, ufs3_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov di, ufs3_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov di, ufs4_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov di, ufs4_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov di, ufs5_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov di, ufs5_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov di, ufs6_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov di, ufs6_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n

    lodsb
    mov [cfg_banner_enabled], al
    lodsb
    mov [cfg_prompt_compact], al
    lodsb
    mov [cfg_theme_index], al
    lodsb
    mov [cfg_color_default], al
    lodsb
    mov [cfg_color_info], al
    lodsb
    mov [cfg_color_warn], al
    lodsb
    mov [cfg_color_error], al
    lodsb
    mov [cfg_color_prompt], al
    lodsb
    mov [cfg_color_ascii], al
    lodsb
    mov [cfg_color_frame], al
    lodsb
    mov [cfg_color_accent], al

    lodsb
    mov [cscript_enabled], al

    mov di, atb_pkg1_name
    mov cx, 33
    call mem_copy_n
    mov di, atb_pkg1_source
    mov cx, 65
    call mem_copy_n
    mov di, atb_pkg1_runtime
    mov cx, 16
    call mem_copy_n

    mov di, atb_pkg2_name
    mov cx, 33
    call mem_copy_n
    mov di, atb_pkg2_source
    mov cx, 65
    call mem_copy_n
    mov di, atb_pkg2_runtime
    mov cx, 16
    call mem_copy_n

    mov di, atb_pkg3_name
    mov cx, 33
    call mem_copy_n
    mov di, atb_pkg3_source
    mov cx, 65
    call mem_copy_n
    mov di, atb_pkg3_runtime
    mov cx, 16
    call mem_copy_n

    lodsb
    mov [region_initialized], al
    lodsb
    mov [timezone_offset], al
    mov di, region_name
    mov cx, REGION_MAX + 1
    call mem_copy_n
    lodsb
    mov [password_initialized], al
    mov di, user_pass_enc
    mov cx, PASS_MAX * 2 + 1
    call mem_copy_n
    mov di, current_dir
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n

    mov byte [username + USER_MAX], 0
    mov byte [current_dir + FS_NAME_MAX], 0
    mov byte [msg_unknown + 63], 0
    mov byte [fs_readme + FS_TEXT_MAX], 0
    mov byte [fs_judges + FS_TEXT_MAX], 0
    mov byte [fs_notes + FS_TEXT_MAX], 0
    mov byte [atb_pkg1_name + 32], 0
    mov byte [atb_pkg2_name + 32], 0
    mov byte [atb_pkg3_name + 32], 0
    mov byte [atb_pkg1_source + 64], 0
    mov byte [atb_pkg2_source + 64], 0
    mov byte [atb_pkg3_source + 64], 0
    mov byte [atb_pkg1_runtime + 15], 0
    mov byte [atb_pkg2_runtime + 15], 0
    mov byte [atb_pkg3_runtime + 15], 0
    mov byte [region_name + REGION_MAX], 0
    mov byte [user_pass_enc + PASS_MAX * 2], 0
    mov byte [ufs1_name + FS_NAME_MAX], 0
    mov byte [ufs2_name + FS_NAME_MAX], 0
    mov byte [ufs3_name + FS_NAME_MAX], 0
    mov byte [ufs4_name + FS_NAME_MAX], 0
    mov byte [ufs5_name + FS_NAME_MAX], 0
    mov byte [ufs6_name + FS_NAME_MAX], 0
    mov byte [ufs1_data + FS_TEXT_MAX], 0
    mov byte [ufs2_data + FS_TEXT_MAX], 0
    mov byte [ufs3_data + FS_TEXT_MAX], 0
    mov byte [ufs4_data + FS_TEXT_MAX], 0
    mov byte [ufs5_data + FS_TEXT_MAX], 0
    mov byte [ufs6_data + FS_TEXT_MAX], 0
    jmp .restore_segments

.init_store:
    mov ax, cs
    mov ds, ax
    mov es, ax
    call fs_store_save

.restore_segments:
    pop es
    pop ds
    ret

fs_store_save:
    push ds
    push es

    mov ax, cs
    mov ds, ax
    mov ax, FS_STORE_SEG
    mov es, ax

    mov di, FS_STORE_BUFFER
    mov si, fs_store_magic
    mov cx, 8
    call mem_copy_n

    mov al, [user_initialized]
    stosb

    mov si, username
    mov cx, USER_MAX + 1
    call mem_copy_n

    mov si, msg_unknown
    mov cx, 64
    call mem_copy_n

    mov si, fs_readme
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n

    mov si, fs_judges
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n

    mov si, fs_notes
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n

    mov si, ufs1_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov si, ufs1_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov si, ufs2_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov si, ufs2_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov si, ufs3_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov si, ufs3_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov si, ufs4_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov si, ufs4_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov si, ufs5_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov si, ufs5_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n
    mov si, ufs6_name
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n
    mov si, ufs6_data
    mov cx, FS_TEXT_MAX + 1
    call mem_copy_n

    mov al, [cfg_banner_enabled]
    stosb
    mov al, [cfg_prompt_compact]
    stosb
    mov al, [cfg_theme_index]
    stosb
    mov al, [cfg_color_default]
    stosb
    mov al, [cfg_color_info]
    stosb
    mov al, [cfg_color_warn]
    stosb
    mov al, [cfg_color_error]
    stosb
    mov al, [cfg_color_prompt]
    stosb
    mov al, [cfg_color_ascii]
    stosb
    mov al, [cfg_color_frame]
    stosb
    mov al, [cfg_color_accent]
    stosb

    mov al, [cscript_enabled]
    stosb

    mov si, atb_pkg1_name
    mov cx, 33
    call mem_copy_n
    mov si, atb_pkg1_source
    mov cx, 65
    call mem_copy_n
    mov si, atb_pkg1_runtime
    mov cx, 16
    call mem_copy_n

    mov si, atb_pkg2_name
    mov cx, 33
    call mem_copy_n
    mov si, atb_pkg2_source
    mov cx, 65
    call mem_copy_n
    mov si, atb_pkg2_runtime
    mov cx, 16
    call mem_copy_n

    mov si, atb_pkg3_name
    mov cx, 33
    call mem_copy_n
    mov si, atb_pkg3_source
    mov cx, 65
    call mem_copy_n
    mov si, atb_pkg3_runtime
    mov cx, 16
    call mem_copy_n

    mov al, [region_initialized]
    stosb
    mov al, [timezone_offset]
    stosb
    mov si, region_name
    mov cx, REGION_MAX + 1
    call mem_copy_n
    mov al, [password_initialized]
    stosb
    mov si, user_pass_enc
    mov cx, PASS_MAX * 2 + 1
    call mem_copy_n
    mov si, current_dir
    mov cx, FS_NAME_MAX + 1
    call mem_copy_n

    mov ax, FS_STORE_LBA
    mov bx, FS_STORE_BUFFER
    mov cx, FS_STORE_SECTORS
    call disk_write_lba_multi

    pop es
    pop ds
    ret

disk_read_lba_multi:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    mov si, ax
    mov di, bx
.read_loop:
    cmp cx, 0
    je .read_ok
    mov ax, si
    mov bx, di
    call disk_read_lba
    jc .read_fail
    inc si
    add di, 512
    dec cx
    jmp .read_loop
.read_ok:
    clc
    jmp .read_done
.read_fail:
    stc
.read_done:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

disk_write_lba_multi:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    mov si, ax
    mov di, bx
.write_loop:
    cmp cx, 0
    je .write_ok
    mov ax, si
    mov bx, di
    call disk_write_lba
    jc .write_fail
    inc si
    add di, 512
    dec cx
    jmp .write_loop
.write_ok:
    clc
    jmp .write_done
.write_fail:
    stc
.write_done:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

disk_read_lba:
    push ax
    push bx
    push cx
    push dx
    push si
    mov si, bx
    call lba_to_chs
    mov bx, si
    mov ah, 0x02
    mov al, 1
    mov dl, [boot_drive]
    int 0x13
    jc .read_one_fail
    clc
    jmp .read_one_done
.read_one_fail:
    stc
.read_one_done:
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

disk_write_lba:
    push ax
    push bx
    push cx
    push dx
    push si
    mov si, bx
    call lba_to_chs
    mov bx, si
    mov ah, 0x03
    mov al, 1
    mov dl, [boot_drive]
    int 0x13
    jc .write_one_fail
    clc
    jmp .write_one_done
.write_one_fail:
    stc
.write_one_done:
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

lba_to_chs:
    push ax
    push bx
    xor dx, dx
    mov bx, 36
    div bx
    mov ch, al
    mov ax, dx
    xor dx, dx
    mov bx, 18
    div bx
    mov dh, al
    mov cl, dl
    inc cl
    pop bx
    pop ax
    ret

get_bios_ticks:
    mov ah, 0x00
    int 0x1A
    mov ax, dx
    mov dx, cx
    ret

get_elapsed_ticks:
    call get_bios_ticks
    sub ax, [boot_ticks]
    sbb dx, [boot_ticks + 2]
    jnc .done
    add ax, 0x00B0
    adc dx, 0x0018
.done:
    ret

clear_screen:
    mov ax, 0x0003
    int 0x10
    ret

exit_cmd:
    ; Fast-path for QEMU with isa-debug-exit device.
    mov dx, 0x0F4
    mov ax, 0x2000
    out dx, ax

    ; Fallback: try ACPI/APM power-off.
    mov ax, 0x5301
    xor bx, bx
    int 0x15
    mov ax, 0x530E
    mov bx, 0x0001
    mov cx, 0x0003
    int 0x15
    mov ax, 0x5307
    mov bx, 0x0001
    mov cx, 0x0003
    int 0x15

    cli
.halt:
    hlt
    jmp .halt

print_string:
    push bx
    mov bl, [cfg_color_default]
    call print_color_string
    pop bx
    ret

print_color_string:
.next_char:
    lodsb
    cmp al, 0
    je .done
    call putc_color
    jmp .next_char
.done:
    ret

print_upper_string:
.next_char:
    lodsb
    cmp al, 0
    je .done
    cmp al, 'a'
    jb .emit
    cmp al, 'z'
    ja .emit
    sub al, 32
.emit:
    call putc_color
    jmp .next_char
.done:
    ret

print_lower_string:
.next_char:
    lodsb
    cmp al, 0
    je .done
    cmp al, 'A'
    jb .emit
    cmp al, 'Z'
    ja .emit
    add al, 32
.emit:
    call putc_color
    jmp .next_char
.done:
    ret

print_u16:
    push ax
    push bx
    push cx
    push dx
    push si

    cmp ax, 0
    jne .convert
    mov al, '0'
    call putc_color
    jmp .done

.convert:
    mov si, 10
    xor cx, cx
.loop:
    xor dx, dx
    div si
    push dx
    inc cx
    cmp ax, 0
    jne .loop
.print:
    pop dx
    mov al, dl
    add al, '0'
    call putc_color
    loop .print

.done:
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

print_bcd_byte:
    push ax
    push bx

    mov ah, al
    shr al, 4
    and al, 0x0F
    add al, '0'
    call putc_color

    mov al, ah
    and al, 0x0F
    add al, '0'
    call putc_color

    pop bx
    pop ax
    ret

bcd_to_bin8:
    push bx
    push cx
    mov ah, al
    and al, 0x0F
    mov bl, al
    mov al, ah
    shr al, 4
    and al, 0x0F
    mov cl, 10
    mul cl
    add al, bl
    pop cx
    pop bx
    ret

print_two_digits:
    push ax
    push cx
    xor ah, ah
    mov cl, 10
    div cl
    add al, '0'
    call putc_color
    mov al, ah
    add al, '0'
    call putc_color
    pop cx
    pop ax
    ret

print_utc_offset:
    push ax
    push dx
    mov dl, al
    cmp dl, 0
    jge .positive
    mov al, '-'
    call putc_color
    mov al, dl
    neg al
    jmp .emit_digits
.positive:
    mov al, '+'
    call putc_color
    mov al, dl
.emit_digits:
    call print_two_digits
    pop dx
    pop ax
    ret

putc_color:
    push ax
    push bx
    push cx
    push dx

    cmp al, 13
    je .teletype
    cmp al, 10
    je .teletype
    cmp al, 8
    je .teletype

    mov ah, 0x09
    mov bh, 0x00
    mov cx, 1
    int 0x10

    mov ah, 0x03
    mov bh, 0x00
    int 0x10
    inc dl
    cmp dl, 80
    jb .set_cursor
    mov dl, 0
    inc dh
    cmp dh, 25
    jb .set_cursor
    call scroll_screen_up_one
    mov dh, 24

.set_cursor:
    mov ah, 0x02
    mov bh, 0x00
    int 0x10
    jmp .done

.teletype:
    mov ah, 0x0E
    mov bh, 0x00
    int 0x10

.done:
    pop dx
    pop cx
    pop bx
    pop ax
    ret

scroll_screen_up_one:
    push ax
    push bx
    push cx
    push dx

    mov ax, 0x0601
    mov bh, [cfg_color_default]
    xor cx, cx
    mov dx, 0x184F
    int 0x10

    pop dx
    pop cx
    pop bx
    pop ax
    ret

read_line:
    mov word [input_limit], MAX_INPUT

read_line_limited:
    xor cx, cx
.read_char:
    mov ah, 0x00
    int 0x16
    cmp al, 0
    je .read_char
    cmp al, 0xE0
    je .read_char
    cmp al, 13
    je .finish
    cmp al, 8
    je .backspace
    cmp cx, [input_limit]
    jae .read_char

    mov [di], al
    inc di
    inc cx
    mov bl, COLOR_DEFAULT
    call putc_color
    jmp .read_char

.backspace:
    cmp cx, 0
    je .read_char
    dec di
    dec cx
    mov byte [di], 0
    call erase_char
    jmp .read_char

.finish:
    mov byte [di], 0
    mov bl, COLOR_DEFAULT
    mov al, 13
    call putc_color
    mov al, 10
    call putc_color
    ret

read_secret_limited:
    xor cx, cx
.read_char:
    mov ah, 0x00
    int 0x16
    cmp al, 0
    je .read_char
    cmp al, 0xE0
    je .read_char
    cmp al, 13
    je .finish
    cmp al, 8
    je .backspace
    cmp cx, [input_limit]
    jae .read_char

    mov [di], al
    inc di
    inc cx
    mov bl, COLOR_DEFAULT
    mov al, '*'
    call putc_color
    jmp .read_char

.backspace:
    cmp cx, 0
    je .read_char
    dec di
    dec cx
    mov byte [di], 0
    call erase_char
    jmp .read_char

.finish:
    mov byte [di], 0
    mov bl, COLOR_DEFAULT
    mov al, 13
    call putc_color
    mov al, 10
    call putc_color
    ret

erase_char:
    push ax
    push bx
    push cx
    push dx

    mov ah, 0x03
    mov bh, 0x00
    int 0x10

    cmp dl, 0
    jne .left
    cmp dh, 0
    je .done
    dec dh
    mov dl, 79
    jmp .set_cursor

.left:
    dec dl

.set_cursor:
    mov ah, 0x02
    mov bh, 0x00
    int 0x10

    mov ah, 0x09
    mov al, ' '
    mov bh, 0x00
    mov bl, COLOR_DEFAULT
    mov cx, 1
    int 0x10

    mov ah, 0x02
    mov bh, 0x00
    int 0x10

.done:
    pop dx
    pop cx
    pop bx
    pop ax
    ret

strcmp:
    push si
    push di
    push bx
.compare:
    mov al, [si]
    mov bl, [di]
    cmp al, bl
    jne .not_equal
    cmp al, 0
    je .equal
    inc si
    inc di
    jmp .compare
.equal:
    mov ax, 1
    jmp .done
.not_equal:
    xor ax, ax
.done:
    pop bx
    pop di
    pop si
    ret

skip_spaces:
.loop:
    cmp byte [si], ' '
    jne .done
    inc si
    jmp .loop
.done:
    ret

strcmd:
    push si
    push di
    push bx
.compare:
    mov al, [di]
    cmp al, 0
    je .boundary
    mov bl, [si]
    cmp al, bl
    jne .no
    inc si
    inc di
    jmp .compare
.boundary:
    mov bl, [si]
    cmp bl, 0
    je .yes
    cmp bl, ' '
    je .yes
.no:
    xor ax, ax
    jmp .done
.yes:
    mov ax, 1
.done:
    pop bx
    pop di
    pop si
    ret

strprefix:
    push si
    push di
    push bx
.loop:
    mov al, [di]
    cmp al, 0
    je .yes
    mov bl, [si]
    cmp bl, 0
    je .no
    cmp al, bl
    jne .no
    inc si
    inc di
    jmp .loop
.yes:
    mov ax, 1
    jmp .done
.no:
    xor ax, ax
.done:
    pop bx
    pop di
    pop si
    ret

copy_string:
.copy:
    lodsb
    mov [di], al
    inc di
    cmp al, 0
    jne .copy
    ret

copy_string_limited:
    cmp cx, 0
    jne .copy
    mov byte [di], 0
    ret
.copy:
    lodsb
    cmp al, 0
    je .done
    mov [di], al
    inc di
    dec cx
    jnz .copy
    mov byte [di], 0
    ret
.done:
    mov [di], al
    ret

string_length:
    xor ax, ax
.loop:
    cmp byte [si], 0
    je .done
    inc si
    inc ax
    jmp .loop
.done:
    ret

count_lines_in_text:
    xor bx, bx
    cmp byte [si], 0
    je .done
    mov bx, 1
.loop:
    mov al, [si]
    cmp al, 0
    je .done
    cmp al, 13
    je .line_break
    cmp al, 10
    je .line_break_single
    inc si
    jmp .loop
.line_break:
    inc si
    cmp byte [si], 10
    jne .line_count
    inc si
.line_count:
    inc bx
    jmp .loop
.line_break_single:
    inc si
    inc bx
    jmp .loop
.done:
    mov ax, bx
    ret

encrypt_password_to_store:
    push ax
    push bx
    push cx
    push dx
    push si
    push di

    mov di, password_work
    mov bx, pass_key
.transform:
    lodsb
    cmp al, 0
    je .transform_done
    add al, 3
    xor al, [bx]
    mov [di], al
    inc di
    inc bx
    cmp byte [bx], 0
    jne .transform
    mov bx, pass_key
    jmp .transform
.transform_done:
    mov byte [di], 0

    mov si, password_work
    call string_length
    mov cx, ax
    mov di, user_pass_enc
    cmp cx, 0
    je .encode_done

    mov bx, cx
.encode_loop:
    dec bx
    js .encode_done
    mov si, password_work
    add si, bx
    mov al, [si]
    call encode_byte_hex
    jmp .encode_loop

.encode_done:
    mov byte [di], 0
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

encode_byte_hex:
    push ax
    mov ah, al
    shr al, 4
    call nibble_to_hex
    mov [di], al
    inc di
    mov al, ah
    and al, 0x0F
    call nibble_to_hex
    mov [di], al
    inc di
    pop ax
    ret

nibble_to_hex:
    cmp al, 9
    jbe .digit
    add al, 'A' - 10
    ret
.digit:
    add al, '0'
    ret

append_line_limited:
    push bx
    push cx
    push dx
    push si
    push di

    mov bx, di
    mov cx, FS_TEXT_MAX
.seek_end:
    cmp cx, 0
    je .fail
    cmp byte [di], 0
    je .at_end
    inc di
    dec cx
    jmp .seek_end

.at_end:
    cmp di, bx
    je .copy_line
    cmp cx, 2
    jb .fail
    mov byte [di], 13
    inc di
    dec cx
    mov byte [di], 10
    inc di
    dec cx

.copy_line:
    cmp cx, 1
    jb .fail
.copy_next:
    lodsb
    cmp al, 0
    je .ok
    cmp cx, 1
    jbe .fail
    mov [di], al
    inc di
    dec cx
    jmp .copy_next

.ok:
    mov byte [di], 0
    mov ax, 1
    jmp .done

.fail:
    xor ax, ax

.done:
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    ret

copy_token_limited:
    cmp cx, 0
    jne .copy
    mov byte [di], 0
    ret
.copy:
    mov al, [si]
    cmp al, 0
    je .done
    cmp al, ' '
    je .done
    mov [di], al
    inc di
    inc si
    dec cx
    jnz .copy
.skip_tail:
    mov al, [si]
    cmp al, 0
    je .done
    cmp al, ' '
    je .done
    inc si
    jmp .skip_tail
.done:
    mov byte [di], 0
    ret

mem_copy_n:
    rep movsb
    ret

mem_equal_n:
    push si
    push di
    repe cmpsb
    jne .no
    mov ax, 1
    jmp .done
.no:
    xor ax, ax
.done:
    pop di
    pop si
    ret

boot_msg db "OpenATB open-source utility by Roman Masovskiy.", 13, 10, 0

cmd_help db "help", 0
cmd_about db "about", 0
cmd_clear db "clear", 0
cmd_cls db "cls", 0
cmd_banner db "banner", 0
cmd_patches db "patches", 0
cmd_sys db "sys", 0
cmd_uptime db "uptime", 0
cmd_time db "time", 0
cmd_date db "date", 0
cmd_version db "version", 0
cmd_fetch db "fetch", 0
cmd_exit db "exit", 0
cmd_echo db "echo", 0
cmd_setname db "setname", 0
cmd_region db "region", 0
cmd_passwd db "passwd", 0
cmd_cd db "cd", 0
cmd_reboot db "reboot", 0
cmd_ls db "ls", 0
cmd_fsls db "fsls", 0
cmd_fsinfo db "fsinfo", 0
cmd_fswrite db "fswrite", 0
cmd_write db "write", 0
cmd_append db "append", 0
cmd_rm db "rm", 0
cmd_touch db "touch", 0
cmd_mk db "mk", 0
cmd_mkdir db "mkdir", 0
cmd_rmdir db "rmdir", 0
cmd_cat db "cat", 0
cmd_nano db "nano", 0
cmd_nano_write db ":w", 0
cmd_nano_save db ":wq", 0
cmd_nano_quit db ":q", 0
cmd_nano_help db ":h", 0

arg_full db "full", 0
arg_raw db "raw", 0
arg_info db "info", 0
arg_root db "/", 0
arg_dotdot db "..", 0
arg_set db "set", 0
arg_reset db "reset", 0
arg_dash_h db "-h", 0
arg_dash_dash_help db "--help", 0

msg_help_title db "[OpenATB open-source utility]", 13, 10, 0
msg_help_core db " core : help about clear cls reboot exit", 13, 10, 0
msg_help_utils db " tools: echo setname region passwd fetch banner", 13, 10, 0
msg_help_info db " info : sys uptime time date version fetch patches", 13, 10, 0
msg_help_fs db " fs   : ls cd touch mk mkdir rmdir nano write append rm cat fsinfo", 13, 10, 0
msg_help_atbman db " atb  : atbman -e/-i/-u/-l", 13, 10, 0
msg_help_patch_retro db " patch: retro-banner", 13, 10, 0
msg_help_patch_alias db " patch: command-hints (?, whoami)", 13, 10, 0
msg_help_patch_hack db " patch: hackathon-demo", 13, 10, 0
msg_help_patch_customize db " patch: customize (c.atb + OpenACT)", 13, 10, 0
msg_help_tip db " includes: 1) OATB DevKit 2) OpenASM-FS 3) OpenACT", 13, 10, 0
msg_unknown_default db "Unknown cmd. Try help.", 0
msg_unknown times 64 db 0
msg_echo_usage db "Usage: echo [-n|-u|-l] <text>", 13, 10, 0
msg_setname_usage db "Usage: setname [<name up to 32 chars>|reset]", 13, 10, 0
msg_setname_ok_prefix db "Username updated: ", 0
msg_setname_reset db "Username reset to guest.", 13, 10, 0
msg_current_user_prefix db "Current user: ", 0
msg_region_usage db "Usage: region [set]", 13, 10, 0
msg_passwd_usage db "Usage: passwd", 13, 10, 0
msg_cd_usage db "Usage: cd [folder|/|..]", 13, 10, 0
msg_cd_now db "Current directory: ", 0
msg_cd_not_found db "OpenASM-FS: directory not found.", 13, 10, 0
msg_banner_usage db "Usage: banner [clear|full]", 13, 10, 0
msg_patches_usage db "Usage: patches [raw]", 13, 10, 0
msg_sys_usage db "Usage: sys <info|time|date|uptime|version|fetch|patches|banner>", 13, 10, 0
msg_cat_usage db "Usage: cat <file>", 13, 10, 0
msg_nano_usage db "Usage: nano <file>", 13, 10, 0
msg_nano_title db "[nano] editing ", 0
msg_nano_existing db "[nano] loaded. Saving rewrites this file.", 13, 10, 0
msg_nano_new_file db "[nano] new file.", 13, 10, 0
msg_nano_prompt_1 db "[nano] multiline mode.", 13, 10, 0
msg_nano_prompt_2 db "[nano] :w save, :wq save+exit, :q quit", 13, 10, 0
msg_nano_prompt_3 db "[nano] commands: :w, :wq, :q, :h", 13, 10, 0
msg_nano_line_prompt db "nano> ", 0
msg_nano_line_limit db "[nano] 1000 lines reached. Use :wq.", 13, 10, 0
msg_nano_size_limit db "[nano] size limit reached. Use :wq.", 13, 10, 0
msg_nano_cancel db "[nano] no changes saved.", 13, 10, 0
msg_nano_written db "[nano] file saved.", 13, 10, 0
msg_fswrite_usage db "Usage: fswrite <file> <text>", 13, 10, 0
msg_append_usage db "Usage: append <file> <text>", 13, 10, 0
msg_rm_usage db "Usage: rm <file>", 13, 10, 0
msg_touch_usage db "Usage: touch|mk <file.ext>", 13, 10, 0
msg_mkdir_usage db "Usage: mkdir <folder>", 13, 10, 0
msg_rmdir_usage db "Usage: rmdir <folder>", 13, 10, 0
msg_touch_ok_prefix db "OpenASM-FS: created file ", 0
msg_touch_exists_prefix db "OpenASM-FS: already exists ", 0
msg_mkdir_ok_prefix db "OpenASM-FS: folder created ", 0
msg_mkdir_exists_prefix db "OpenASM-FS: folder exists ", 0
msg_mkdir_invalid db "OpenASM-FS: invalid folder name.", 13, 10, 0
msg_rmdir_ok_prefix db "OpenASM-FS: folder removed ", 0
msg_rmdir_not_found_prefix db "OpenASM-FS: folder not found ", 0
msg_rmdir_not_empty_prefix db "OpenASM-FS: folder is not empty ", 0
msg_fs_full db "OpenASM-FS: user file table full (6 max).", 13, 10, 0
msg_fswrite_ok db "OpenASM-FS: file updated.", 13, 10, 0
msg_fswrite_user_ok db "OpenASM-FS: user profile updated.", 13, 10, 0
msg_append_ok db "OpenASM-FS: text appended.", 13, 10, 0
msg_rm_ok db "OpenASM-FS: file deleted permanently.", 13, 10, 0
msg_rm_dir_hint db "Use rmdir <folder> for folders.", 13, 10, 0
msg_file_not_found db "OpenASM-FS: file not found.", 13, 10, 0
msg_path_invalid db "OpenASM-FS: invalid path.", 13, 10, 0
msg_dir_missing db "OpenASM-FS: parent folder is missing.", 13, 10, 0
msg_setup_top db "+-------------------------------------------------------+", 13, 10, 0
msg_setup_title db "|            OpenATB Setup Wizard (vintage)            |", 13, 10, 0
msg_setup_sep db "+-------------------------------------------------------+", 13, 10, 0
msg_setup_line_1 db "| Configure profile, region and security for OpenATB.  |", 13, 10, 0
msg_setup_line_2 db "| Use Enter to confirm each step.                      |", 13, 10, 0
msg_setup_bottom db "+-------------------------------------------------------+", 13, 10, 0
msg_setup_step_user db "[Step 1/3] User profile", 13, 10, 0
msg_setup_step_region db "[Step 2/3] Region / time zone", 13, 10, 0
msg_setup_step_pass db "[Step 3/3] Password", 13, 10, 0
msg_setup_done db "+-------------------------------------------------------+", 13, 10, "| Setup complete. Entering OpenATB shell.              |", 13, 10, "+-------------------------------------------------------+", 13, 10, 0
msg_pick_name db "First boot setup: choose username (max 32, empty = guest): ", 0
msg_pick_region_title db "First boot setup: choose region:", 13, 10, 0
msg_pick_region_choice db "Region [1-7]: ", 0
msg_region_opt_1 db " 1) Pacific (UTC-08)", 13, 10, 0
msg_region_opt_2 db " 2) Eastern (UTC-05)", 13, 10, 0
msg_region_opt_3 db " 3) UTC (UTC+00)", 13, 10, 0
msg_region_opt_4 db " 4) Central Europe (UTC+01)", 13, 10, 0
msg_region_opt_5 db " 5) Moscow (UTC+03)", 13, 10, 0
msg_region_opt_6 db " 6) Singapore (UTC+08)", 13, 10, 0
msg_region_opt_7 db " 7) Tokyo (UTC+09)", 13, 10, 0
msg_region_set_prefix db "Region set: ", 0
msg_region_current_prefix db "Region: ", 0
msg_region_offset_prefix db " (UTC", 0
msg_region_offset_suffix db ")", 0
msg_pick_pass db "First boot setup: set password (max 32): ", 0
msg_pass_set db "Password saved (encrypted).", 13, 10, 0
msg_hello_prefix db "Welcome, ", 0
msg_hello_suffix db "! Your profile is now mounted in OpenASM-FS.", 13, 10, 0
msg_boot_notice_line_1 db "[ OpenATB ] visual shell online: gradients, cards, colorized ls.", 13, 10, 0
msg_boot_notice_line_2 db "[ OpenATB ] [DIR]=amber [FILE]=green [CORE]=cyan | DevKit fs+.", 13, 10, 13, 10, 0
msg_userfile_prefix db "user.txt => ", 0
msg_uptime_prefix db "Uptime: ", 0
msg_uptime_suffix db " min", 13, 10, 0
msg_time_prefix db "Time: ", 0
msg_date_prefix db "Date: ", 0
msg_version db "OpenATB runtime v0.3.0", 13, 10, 0
msg_fetch_head db "[OpenATB fetch]", 13, 10, 0
msg_fetch_logo_1 db "   O P E N A T B", 13, 10, 0
msg_fetch_logo_2 db "   open-source utility card", 13, 10, 0
msg_fetch_logo_3 db "   by Roman Masovskiy", 13, 10, 0
msg_fetch_product db " utility: OpenATB (Open Assembly ToolBox)", 13, 10, 0
msg_fetch_component_1 db " 1) OATB DevKit   - app/dev instructions", 13, 10, 0
msg_fetch_component_2 db " 2) OpenASM-FS    - assembly filesystem", 13, 10, 0
msg_fetch_component_3 db " 3) OpenACT (c.atb) - graphical customization", 13, 10, 0
msg_fetch_user db " user   : ", 0
msg_fetch_cwd db " cwd    : ", 0
msg_fetch_region db " region : ", 0
msg_fetch_uptime db " uptime : ", 0
msg_fetch_fs db " fs     : dirs=", 0
msg_fetch_dirs_sep db " files=", 0
msg_fetch_files_tail db " (core=4)", 13, 10, 0
msg_fetch_auth db " auth   : ", 0
msg_fetch_auth_on db "configured", 0
msg_fetch_auth_off db "not set", 0
msg_fetch_tz db " UTC", 0
msg_rtc_fail db "RTC is unavailable on this machine.", 13, 10, 0
msg_patches_title db "[Patch status]", 13, 10, 0
msg_patches_raw_title db "[Patch status raw: 1=enabled, 0=disabled]", 13, 10, 0
msg_patch_raw_retro db " retro-banner   = ", 0
msg_patch_raw_hints db " command-hints  = ", 0
msg_patch_raw_hack db " hackathon-demo = ", 0
msg_patch_raw_customize db " customize      = ", 0
msg_patch_state_retro db " retro-banner   : green=on, red=off", 13, 10, 0
msg_patch_state_hints db " command-hints  : green=on, red=off", 13, 10, 0
msg_patch_state_hack db " hackathon-demo : green=on, red=off", 13, 10, 0
msg_patch_state_customize db " customize      : green=on, red=off", 13, 10, 0
msg_newline db 13, 10, 0
prompt_tail db "@OATB> ", 0
prompt_tail_compact db "# ", 0

msg_fs_title db "OpenASM-FS mounted files:", 13, 10, 0
msg_fs_legend db " legend: [CORE]=system files, [FILE]=user files, [DIR]=folders", 13, 10, 0
msg_fsinfo_title db "[OpenASM-FS]", 13, 10, 0
msg_fsinfo_line_1 db " core : readme.txt judges.txt user.txt notes.txt", 13, 10, 0
msg_fsinfo_line_2 db " user : cd, touch/mk, mkdir/rmdir, nano, write, append, cat, rm", 13, 10, 0
msg_fsinfo_line_3 db " path : folder/file.ext (one level folders)", 13, 10, 0
fs_entry_readme db " [CORE] readme.txt", 13, 10, 0
fs_entry_judges db " [CORE] judges.txt", 13, 10, 0
fs_entry_user db " [CORE] user.txt", 13, 10, 0
fs_entry_notes db " [CORE] notes.txt", 13, 10, 0
msg_fs_file_prefix db " [FILE] ", 0
msg_fs_dir_prefix db " [DIR ] ", 0

fs_name_readme db "readme.txt", 0
fs_name_judges db "judges.txt", 0
fs_name_user db "user.txt", 0
fs_name_notes db "notes.txt", 0
region_name_pacific db "Pacific", 0
region_name_eastern db "Eastern", 0
region_name_utc db "UTC", 0
region_name_cet db "Central Europe", 0
region_name_moscow db "Moscow", 0
region_name_sg db "Singapore", 0
region_name_tokyo db "Tokyo", 0
default_password db "openatb", 0
pass_key db "OATB26", 0

fs_readme_default db "OpenASM-FS: tiny in-memory FS with live editing.", 0
fs_judges_default db "Roman note: tuned for real demos and practical tweaks.", 0
fs_readme times FS_TEXT_MAX + 1 db 0
fs_judges times FS_TEXT_MAX + 1 db 0
fs_notes times FS_TEXT_MAX + 1 db 0
ufs1_name times FS_NAME_MAX + 1 db 0
ufs1_data times FS_TEXT_MAX + 1 db 0
ufs2_name times FS_NAME_MAX + 1 db 0
ufs2_data times FS_TEXT_MAX + 1 db 0
ufs3_name times FS_NAME_MAX + 1 db 0
ufs3_data times FS_TEXT_MAX + 1 db 0
ufs4_name times FS_NAME_MAX + 1 db 0
ufs4_data times FS_TEXT_MAX + 1 db 0
ufs5_name times FS_NAME_MAX + 1 db 0
ufs5_data times FS_TEXT_MAX + 1 db 0
ufs6_name times FS_NAME_MAX + 1 db 0
ufs6_data times FS_TEXT_MAX + 1 db 0

banner_top db "+----------------------------------------------------------------+", 13, 10, 0
art_line_1 db "|                                                                |", 13, 10, 0
art_line_2 db "|    OOO   PPPP  EEEEE N   N   AAA  TTTTT BBBB                   |", 13, 10, 0
art_line_3 db "|   O   O  P   P E     NN  N  A   A   T   B   B                  |", 13, 10, 0
art_line_4 db "|   O   O  PPPP  EEEE  N N N  AAAAA   T   BBBB                   |", 13, 10, 0
art_line_5 db "|   O   O  P     E     N  NN  A   A   T   B   B                  |", 13, 10, 0
art_line_6 db "|    OOO   P     EEEEE N   N  A   A   T   BBBB                   |", 13, 10, 0
banner_bottom db "+----------------------------------------------------------------+", 13, 10, 0
fs_tagline db "            OpenASM-FS * by Roman Masovskiy", 13, 10, 13, 10, 0

about_top db "+-------------------------------------------------------+", 13, 10, 0
about_title db "|             OpenATB Open-Source Utility              |", 13, 10, 0
about_sep db "+-------------------------------------------------------+", 13, 10, 0
about_line_1 db "  1) OATB DevKit  : instruction set for OpenATB apps", 13, 10, 0
about_line_2 db "  2) OpenASM-FS   : assembly filesystem for OpenATB", 13, 10, 0
about_line_3 db "  3) OpenACT c.atb: graphical customization toolbox", 13, 10, 0
about_user_prefix db "  User   : ", 0
about_user_suffix db 13, 10, 0
about_bottom db "+-------------------------------------------------------+", 13, 10, 0

patch_state_retro_color db COLOR_ERROR
patch_state_hints_color db COLOR_ERROR
patch_state_hack_color db COLOR_ERROR
patch_state_customize_color db COLOR_ERROR

cfg_banner_enabled db 1
cfg_prompt_compact db 0
cfg_theme_index db 0
cfg_color_default db COLOR_DEFAULT
cfg_color_info db COLOR_INFO
cfg_color_warn db COLOR_WARN
cfg_color_error db COLOR_ERROR
cfg_color_prompt db COLOR_PROMPT
cfg_color_ascii db COLOR_ASCII
cfg_color_frame db COLOR_FRAME
cfg_color_accent db COLOR_ACCENT

fs_store_magic db "OAFS1", 0, 0, 0
boot_drive db 0
boot_ticks dd 0
time_hour db 0
time_min db 0
time_sec db 0
input_limit dw MAX_INPUT
nano_line_count dw 0
fs_token times FS_NAME_MAX + 1 db 0
dir_token times FS_NAME_MAX + 1 db 0
dir_marker times FS_NAME_MAX + 1 db 0
current_dir times FS_NAME_MAX + 1 db 0
nano_buffer times FS_TEXT_MAX + 1 db 0
default_user db "guest", 0
region_initialized db 0
timezone_offset db 0
region_name times REGION_MAX + 1 db 0
password_initialized db 0
user_pass_enc times PASS_MAX * 2 + 1 db 0
password_plain times PASS_MAX + 1 db 0
password_work times PASS_MAX + 1 db 0
setup_touched db 0
user_initialized db 0
username times USER_MAX + 1 db 0
; OATB_PATCH_KERNEL_DATA
; OATB_PATCH_APPLIED_customize_4
cmd_atbman db "atbman", 0
arg_dash_i db "-i", 0
arg_dash_u db "-u", 0
arg_dash_l db "-l", 0
arg_dash_e db "-e", 0
arg_dash_dash_exec db "--exec", 0
arg_dash_dash_install db "--install", 0
arg_dash_dash_uninstall db "--uninstall", 0
arg_dash_dash_list db "--list", 0
fs_name_cscript db "c.atb", 0
fs_name_custom_yaml db "customization.yaml", 0
fs_entry_cscript db " - c.atb", 13, 10, 0
fs_entry_custom_yaml db " - customization.yaml", 13, 10, 0
cscript_enabled db 0
atb_source_default db "manual://local", 0
atb_source_core db "core://openatb", 0
atb_source_local db "local://openasm-fs", 0
msg_atbman_ls_dash db " - ", 0
msg_atbman_usage db "atbman (std .atb manager): execute local or installed .atb via -e", 13, 10, " usage: -e <pkg.atb> | -i <pkg.atb> [source] [runtime] | -u <pkg.atb> | -l", 13, 10, " devkit: if/else, oatb.system.run(), oatb.system.clear, oatb.menu.*, oatb.fs.write/append/read", 13, 10, 0
msg_atbman_example_exec db "  ex: atbman -e c.atb  (launch OpenACT)", 13, 10, 0
msg_atbman_example_install db "  ex: atbman -i cooltheme.atb https://github.com/user/repo python", 13, 10, 0
msg_atbman_example_uninstall db "  ex: atbman -u cooltheme.atb", 13, 10, 0
msg_atbman_exec_prefix db "[atbman] running ", 0
msg_atbman_exec_from db " from ", 0
msg_atbman_runtime_prefix db " runtime: ", 0
msg_atbman_exec_done db "[atbman] program finished.", 13, 10, 0
msg_atbman_exec_missing_prefix db "[atbman] package not installed: ", 0
msg_atbman_exec_cscript db "[atbman] launching OpenACT from c.atb...", 13, 10, 0
msg_atbman_runtime_python_hint db " [bridge] python app: install host runtime via `oatb app install python`.", 13, 10, 0
msg_atbman_runtime_c_hint db " [bridge] c app: compile/run via host toolchain (gcc/clang).", 13, 10, 0
msg_atb_run_host_prefix db " [bridge] host runtime: ", 0
msg_atb_run_host_cmd db " :: cmd=", 0
msg_atb_menu_frame db "+------------------------------------------------+", 13, 10, 0
msg_atb_menu_item_prefix db " - ", 0
msg_atb_menu_prompt db "menu> ", 0
msg_atbman_install_ok_prefix db "[atbman] installed ", 0
msg_atbman_install_from db " from ", 0
msg_atbman_install_runtime db " runtime=", 0
msg_atbman_install_exists_prefix db "[atbman] already installed: ", 0
msg_atbman_install_full db "[atbman] registry full (max 3 user packages).", 13, 10, 0
msg_atbman_uninstall_ok_prefix db "[atbman] removed ", 0
msg_atbman_uninstall_missing_prefix db "[atbman] not installed: ", 0
msg_atbman_core_present db "[atbman] c.atb is core and already available.", 13, 10, 0
msg_atbman_core_protected db "[atbman] c.atb is core and cannot be removed.", 13, 10, 0
msg_atbman_unknown_fallback db "Unknown command. Type help.", 0
msg_atbman_cat_pkg_prefix db "[atbman] package: ", 0
msg_atbman_list_title db "[atbman registry]", 13, 10, 0
msg_atbman_list_sep db " <- ", 0
msg_atbman_list_runtime_sep db " :: ", 0
msg_atbman_list_none db " (no user-installed packages)", 13, 10, 0
runtime_atbdevkit db "atbdevkit", 0
runtime_python db "python", 0
runtime_python3 db "python3", 0
runtime_c db "c", 0
runtime_generic db "native", 0
atb_devkit_cmd_func db "func ", 0
atb_devkit_cmd_else db "else", 0
atb_devkit_cmd_if db "if ", 0
atb_devkit_cmd_output1 db "oatb.system.output => ", 0
atb_devkit_cmd_output2 db "output() => ", 0
atb_devkit_cmd_output3 db "output(", 0
atb_devkit_cmd_run1 db "oatb.system.run => ", 0
atb_devkit_cmd_run2 db "oatb.system.run(", 0
atb_devkit_cmd_clear db "oatb.system.clear", 0
atb_devkit_cmd_menu_title db "oatb.menu.title => ", 0
atb_devkit_cmd_menu_item db "oatb.menu.item => ", 0
atb_devkit_cmd_menu_input db "oatb.menu.input => ", 0
atb_devkit_cmd_var db "var ", 0
atb_devkit_cmd_write db "oatb.fs.write => ", 0
atb_devkit_cmd_append db "oatb.fs.append => ", 0
atb_devkit_cmd_read db "oatb.fs.read => ", 0
atb_devkit_expr_input db "input()", 0
atb_name_a db "a", 0
atb_name_b db "b", 0
atb_name_user_choice db "user_choice", 0
c_atb_script_view db "<OATB DevKit app :: c.atb>", 13, 10, "app :: openact.customizer", 13, 10, "meta :: author :: Roman Masovskiy", 13, 10, "meta :: mode :: full-customize", 13, 10, "oatb.system.clear", 13, 10, "oatb.theme.set => amber", 13, 10, "oatb.ui.open => openact", 13, 10, 0
customization_yaml_view db "version: 1", 13, 10, "profile: default", 13, 10, "theme: classic", 13, 10, "menu: OpenACT", 13, 10, 0
msg_openact_title db "[OpenACT - Open Assembly Customization ToolBox]", 13, 10, 0
msg_openact_credit db " Credits in banner/about are fixed: Roman Masovskiy", 13, 10, 0
msg_openact_banner db " 1) Banner        : ", 0
msg_openact_theme db " 2) Color theme   : ", 0
msg_openact_prompt db " 3) Prompt mode   : ", 0
msg_openact_user db " 4) Username      : ", 0
msg_openact_opt_readme db " 5) Edit readme.txt", 13, 10, 0
msg_openact_opt_judges db " 6) Edit judges.txt", 13, 10, 0
msg_openact_opt_unknown db " 7) Edit unknown command message", 13, 10, 0
msg_openact_keys db " Keys: 1/2/3/4/5/6/7, R reset profile, S save+exit", 13, 10, 0
msg_openact_on db "on", 0
msg_openact_off db "off", 0
msg_openact_theme_classic db "classic", 0
msg_openact_theme_ice db "ice", 0
msg_openact_theme_amber db "amber", 0
msg_openact_prompt_classic db "classic", 0
msg_openact_prompt_compact db "compact", 0
msg_openact_enter_user db "OpenACT> set username (empty=guest): ", 0
msg_openact_enter_readme db "OpenACT> readme.txt text: ", 0
msg_openact_enter_judges db "OpenACT> judges.txt text: ", 0
msg_openact_enter_unknown db "OpenACT> unknown-command text: ", 0
msg_openact_saved db "[OpenACT] settings applied.", 13, 10, 0
msg_openact_reset_done db "[OpenACT] c.atb profile restored.", 13, 10, 0
atb_exec_src_ptr dw 0
atb_quote_state db 0
atb_line_buf times FS_TEXT_MAX + 1 db 0
atb_exec_buf times FS_TEXT_MAX + 1 db 0
atb_tmp_token times 33 db 0
atb_if_left times 33 db 0
atb_if_rhs dw 0
atb_if_pending db 0
atb_if_result db 0
atb_int_a dw 0
atb_int_b dw 0
atb_int_user_choice dw 0
atb_var_name times 33 db 0
atb_var_value times FS_TEXT_MAX + 1 db 0
atb_arg_name times 33 db 0
atb_arg_source times 65 db 0
atb_arg_runtime times 16 db 0
atb_pkg1_name times 33 db 0
atb_pkg1_source times 65 db 0
atb_pkg1_runtime times 16 db 0
atb_pkg2_name times 33 db 0
atb_pkg2_source times 65 db 0
atb_pkg2_runtime times 16 db 0
atb_pkg3_name times 33 db 0
atb_pkg3_source times 65 db 0
atb_pkg3_runtime times 16 db 0

input_buffer times MAX_INPUT + 1 db 0
