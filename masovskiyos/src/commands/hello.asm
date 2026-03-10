; Command: hello
; Description: Simple greeting command template.
; Hook this handler from your kernel dispatch logic.

hello_cmd:
    mov si, hello_msg
    call print_string
    ret

hello_msg db "[hello] stub command. Put your logic here.", 13, 10, 0
