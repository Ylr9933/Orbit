"""Minimal CUDA driver computation for a bounded container smoke."""

from typing import Any


def main() -> None:
    import ctypes as C

    cuda = C.CDLL("libcuda.so.1")

    def call(name: str, argtypes: list[Any], *args: Any) -> None:
        function = getattr(cuda, name)
        function.argtypes = argtypes
        function.restype = C.c_int
        status = function(*args)
        if status != 0:
            raise RuntimeError(f"{name} failed with CUDA status {status}")

    pointer = C.c_void_p
    size = C.c_size_t
    u64 = C.c_uint64
    u32 = C.c_uint
    integer = C.c_int
    call("cuInit", [u32], 0)
    count = integer()
    call("cuDeviceGetCount", [C.POINTER(integer)], C.byref(count))
    assert count.value == 1, f"expected one visible GPU, got {count.value}"
    device = integer()
    call("cuDeviceGet", [C.POINTER(integer), integer], C.byref(device), 0)
    name = C.create_string_buffer(100)
    call("cuDeviceGetName", [pointer, integer, integer], name, 100, device)
    context = pointer()
    call("cuCtxCreate_v2", [C.POINTER(pointer), u32, integer], C.byref(context), 0, device)
    ptx = b"""
.version 7.0
.target sm_50
.address_size 64
.visible .entry add_kernel(.param .u64 out, .param .u64 left, .param .u64 right) {
  .reg .b64 %rd<4>;
  .reg .f32 %f<4>;
  ld.param.u64 %rd1, [out];
  ld.param.u64 %rd2, [left];
  ld.param.u64 %rd3, [right];
  ld.global.f32 %f1, [%rd2];
  ld.global.f32 %f2, [%rd3];
  add.f32 %f3, %f1, %f2;
  st.global.f32 [%rd1], %f3;
  ret;
}
"""
    module = pointer()
    call("cuModuleLoadData", [C.POINTER(pointer), pointer], C.byref(module), C.c_char_p(ptx))
    function = pointer()
    call(
        "cuModuleGetFunction",
        [C.POINTER(pointer), pointer, C.c_char_p],
        C.byref(function),
        module,
        b"add_kernel",
    )
    allocations = []
    for value in (0.0, 1.25, 2.5):
        address = u64()
        call("cuMemAlloc_v2", [C.POINTER(u64), size], C.byref(address), 4)
        allocations.append(address)
        host = C.c_float(value)
        call("cuMemcpyHtoD_v2", [u64, pointer, size], address, C.byref(host), 4)
    params = (pointer * 3)(*[C.cast(C.byref(value), pointer) for value in allocations])
    call(
        "cuLaunchKernel",
        [pointer, u32, u32, u32, u32, u32, u32, u32, pointer, C.POINTER(pointer), pointer],
        function,
        1,
        1,
        1,
        1,
        1,
        1,
        0,
        None,
        params,
        None,
    )
    call("cuCtxSynchronize", [])
    answer = C.c_float()
    call("cuMemcpyDtoH_v2", [pointer, u64, size], C.byref(answer), allocations[0], 4)
    assert answer.value == 3.75, answer.value
    print(f"CUDA computation passed: 1.25 + 2.5 = {answer.value}; GPU={name.value.decode()}")
    for address in allocations:
        call("cuMemFree_v2", [u64], address)
    call("cuModuleUnload", [pointer], module)
    call("cuCtxDestroy_v2", [pointer], context)


if __name__ == "__main__":
    main()
