#if defined(__GNUC__) && !defined(__HGGCCC__)
#include "hggc_library_types.h"
#include "hggc_runtime_api.hpp"
#else
#include_next "hggc_runtime.h"
#endif
