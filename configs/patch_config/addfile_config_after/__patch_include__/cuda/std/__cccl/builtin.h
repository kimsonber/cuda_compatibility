
#include_next <cuda/std/__cccl/builtin.h>

#if __has_include(<cuda/std/__cccl/version.h>)
#include <cuda/std/__cccl/version.h>

#if CCCL_VERSION >= 2008000
#undef _CCCL_BUILTIN_INTEGER_PACK
#undef _CCCL_BUILTIN_MAKE_INTEGER_SEQ
#undef _CCCL_BUILTIN_REMOVE_REFERENCE_T
#endif // CCCL_VERSION >= 2008000

#if CCCL_VERSION >= 3000000
#undef _CCCL_BUILTIN_REFERENCE_CONSTRUCTS_FROM_TEMPORARY
#undef _CCCL_BUILTIN_REFERENCE_CONVERTS_FROM_TEMPORARY
#endif // CCCL_VERSION >= 3000000

#endif // __has_include(<cuda/std/__cccl/version.h>)
