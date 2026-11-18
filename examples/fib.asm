format ELF64 executable 3
segment readable executable
print:
mov     r9, -3689348814741910323
sub     rsp, 40
mov     BYTE [rsp+31], 10
lea     rcx, [rsp+30]
.L2:
mov     rax, rdi
lea     r8, [rsp+32]
mul     r9
mov     rax, rdi
sub     r8, rcx
shr     rdx, 3
lea     rsi, [rdx+rdx*4]
add     rsi, rsi
sub     rax, rsi
add     eax, 48
mov     BYTE [rcx], al
mov     rax, rdi
mov     rdi, rdx
mov     rdx, rcx
sub     rcx, 1
cmp     rax, 9
ja      .L2
lea     rax, [rsp+32]
mov     edi, 1
sub     rdx, rax
xor     eax, eax
lea     rsi, [rsp+32+rdx]
mov     rdx, r8
mov     rax, 1
syscall
add     rsp, 40
ret
addr0:
pop rax
mov [r15-8], rax
sub r15, 8
mov rax, 0
push rax
mov rax, 1
push rax
addr3:
push QWORD [rsp+8]
mov rax, 4000000
push rax
mov rcx, 0
mov rdx, 1
pop rbx
pop rax
cmp rax, rbx
cmovl rcx, rdx
push rcx
pop rax
test rax, rax
jz addr18
sub r15, 16
pop rax
mov [r15+8], rax
pop rax
mov [r15+0], rax
push QWORD [r15+0]
pop rdi
call print
push QWORD [r15+8]
push QWORD [r15+0]
push QWORD [r15+8]
pop rax
add [rsp], rax
add r15, 16
jmp addr3
addr18:
pop rax
pop rax
add r15, 8
push QWORD [r15-8]
ret
entry start
start:
mov [args_ptr], rsp
mov r15, ret_stack+65536
call addr0
mov rax, 60
mov rdi, 0
syscall
segment readable writable
args_ptr: rq 1
ret_stack: rb 65536
mem: rb 0
