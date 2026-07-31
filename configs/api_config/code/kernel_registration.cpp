// Please don't modify this file directly. It is generated automatically
#include <string>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <memory.h>
#include <cuda_runtime_api.h>
#if !defined(__HGGCRT_H__) && __has_include("hggc_runtime_api.h")
    #include <hggc_runtime_api.h>
#elif !defined(_HGGC_RUNTIME_API_H_) &&  __has_include("hggcrt.h")
    #include <hggcrt.h>
#endif

extern "C" {

static bool gInitialized = false;
static bool gTraceFuncCall = false;
static bool checkTrace = false;
static void* pHandle = NULL;

typedef unsigned    (*PFNPushCallConfiguration)(dim3 gridDim, dim3 blockDim, size_t sharedMem, void *stream);
typedef cudaError_t (*PFNPopCallConfiguration)(dim3 *gridDim, dim3 *blockDim, size_t *sharedMem, void *stream);
typedef void        (*PFNRegisterFunction)(void **fatCubinHandle, const char *hostFun, char *deviceFun, const char *deviceName, int thread_limit, uint3 *tid, uint3 *bid, dim3 *bDim, dim3 *gDim, int *wSize);
typedef void**      (*PFNRegisterFatBinary)(void *fatCubin);
typedef void        (*PFNUnregisterFatBinary)(void **fatCubinHandle);
typedef void        (*PFNRegisterVar)(void **fatCubinHandle, char *hostVar, char *deviceAddress, const char *deviceName, int ext, size_t size, int constant, int global);
typedef void        (*PFNRegisterManagedVar)(void **fatCubinHandle, void **hostVarPtrAddress, char *deviceAddress, const char *deviceName, int ext, size_t size, int constant, int global);
typedef char        (*PFNInitModule)(void **fatCubinHandle);
typedef void        (*PFNRegisterTexture)(void **fatCubinHandle, const struct textureReference *hostVar, const void **deviceAddress, const char *deviceName, int dim, int norm, int ext);

struct hggcInterface {
    //Func pointers to HGGC Impl
    PFNPushCallConfiguration  pushCallConfiguration;
    PFNPopCallConfiguration   popCallConfiguration;
    PFNRegisterFunction       registerFunction;
    PFNRegisterFatBinary      registerFatBinary;
    PFNUnregisterFatBinary    unregisterFatBinary;
    PFNRegisterVar            registerVar;
    PFNRegisterManagedVar     registerManagedVar;
    PFNRegisterTexture        registerTexture;
    PFNInitModule             initModule;
};

static struct hggcInterface g_interface;

static bool Initialize() {
    if (gInitialized) {
        return true;
    }

    const char* pFile = NULL;
    bool isFakePath = false;

    const char* LibraryName = "libhggcrt.12.0.so";
    const char* FakeLibraryName = "libfake_runtime.so";
    #if defined (CUDA_VERSION_INSTALL) && CUDA_VERSION_INSTALL >= 13000
        LibraryName = "libhggcrt.13.0.so";
        FakeLibraryName = "libfake_runtime13.so";
    #endif
    const char* selector = getenv("HGGC_DRIVER_CANDIDATE");
    if (selector && (strcmp(selector, "FAKE") == 0)) {
          pFile = FakeLibraryName;
          isFakePath = true;
    } else if (selector && (strcmp(selector, "UMD") == 0)) {
        pFile = LibraryName;
    } else {
        pFile = LibraryName;
    }


    pHandle = dlopen(pFile, RTLD_LAZY);
    if (!pHandle && strncmp(pFile, "libhggcrt.", strlen("libhggcrt.")) == 0) {
        pHandle = dlopen("libhggcrt1.so", RTLD_LAZY);
    }

    if ((!pHandle) && isFakePath) {
        pFile = "libfake_driver.so";
        pHandle = dlopen(pFile, RTLD_LAZY);
    }
    if (!pHandle) {
        printf("cannot open the file:%s  with error %s\n", pFile, dlerror());
        return false;
    }

    g_interface.pushCallConfiguration = reinterpret_cast<PFNPushCallConfiguration>(dlsym(pHandle, "__hggcPushCallConfiguration"));
    g_interface.popCallConfiguration  = reinterpret_cast<PFNPopCallConfiguration >(dlsym(pHandle, "__hggcPopCallConfiguration" ));
    g_interface.registerFunction      = reinterpret_cast<PFNRegisterFunction     >(dlsym(pHandle, "__hggcRegisterFunction"     ));
    g_interface.registerFatBinary     = reinterpret_cast<PFNRegisterFatBinary    >(dlsym(pHandle, "__hggcRegisterFatBinary"    ));
    g_interface.unregisterFatBinary   = reinterpret_cast<PFNUnregisterFatBinary  >(dlsym(pHandle, "__hggcUnregisterFatBinary"  ));
    g_interface.registerVar           = reinterpret_cast<PFNRegisterVar          >(dlsym(pHandle, "__hggcRegisterVar"          ));
    g_interface.registerManagedVar    = reinterpret_cast<PFNRegisterManagedVar   >(dlsym(pHandle, "__hggcRegisterManagedVar"   ));
    g_interface.registerTexture       = reinterpret_cast<PFNRegisterTexture      >(dlsym(pHandle, "__hggcRegisterTexture"      ));
    g_interface.initModule            = reinterpret_cast<PFNInitModule           >(dlsym(pHandle, "__hggcInitModule"           ));

    gInitialized = true;
    return true;
}

static void TraceCall(const char* func) {
    // Only Check Once
    if (!checkTrace) {
        checkTrace = true;
        const char* trace_func_call = getenv("TRACE_FUNC_CALL");
        if (trace_func_call != NULL && trace_func_call != "")
            gTraceFuncCall = true;
    }

    if (gTraceFuncCall) {
        printf("FakeLib Call Func: %s\n", func);
    }
}

unsigned CUDARTAPI __cudaPushCallConfiguration(dim3 gridDim, dim3 blockDim, size_t sharedMem, void *stream) {
    Initialize();
    if (g_interface.pushCallConfiguration != NULL) {
        return g_interface.pushCallConfiguration(gridDim, blockDim, sharedMem, stream);
    }
    return cudaErrorNotSupported;
}

cudaError_t CUDARTAPI __cudaPopCallConfiguration(dim3 *gridDim, dim3 *blockDim, size_t *sharedMem, void *stream) {
    Initialize();
    if (g_interface.popCallConfiguration != NULL) {
        return g_interface.popCallConfiguration(gridDim, blockDim, sharedMem, stream);
    }
    return cudaErrorNotSupported;
}

void CUDARTAPI __cudaRegisterFunction(void **fatCubinHandle, const char *hostFun, char *deviceFun, const char *deviceName, int thread_limit, uint3 *tid, uint3 *bid, dim3 *bDim, dim3 *gDim, int *wSize) {
    Initialize();
    if (g_interface.registerFunction != NULL) {
        g_interface.registerFunction(fatCubinHandle, hostFun, deviceFun, deviceName, thread_limit, tid, bid, bDim, gDim, wSize);
    }
}

void** CUDARTAPI __cudaRegisterFatBinary(void *fatCubin) {
    Initialize();
    if (g_interface.registerFatBinary != NULL) {
        return g_interface.registerFatBinary(fatCubin);
    }
    return NULL;
}

void CUDARTAPI __cudaRegisterFatBinaryEnd(void **fatCubinHandle) {
    fprintf(stderr, "%s __cudaRegisterFatBinaryEnd called, loaded a CUDA binary?\n", __func__);
    exit(1);
}

void CUDARTAPI __cudaUnregisterFatBinary(void **fatCubinHandle) {
    Initialize();
    if (g_interface.unregisterFatBinary != NULL) {
        g_interface.unregisterFatBinary(fatCubinHandle);
    }
}

void CUDARTAPI __cudaRegisterVar(void **fatCubinHandle, char *hostVar, char *deviceAddress, const char *deviceName, int ext, size_t size, int constant, int global) {
    Initialize();
    if (g_interface.registerVar != NULL) {
        g_interface.registerVar(fatCubinHandle, hostVar, deviceAddress, deviceName, ext, size, constant, global);
    }
}

void CUDARTAPI __cudaRegisterManagedVar(
        void **fatCubinHandle,
        void **hostVarPtrAddress,
        char  *deviceAddress,
        const char  *deviceName,
        int    ext,
        size_t size,
        int    constant,
        int    global) {
    Initialize();
    if (g_interface.registerManagedVar != NULL) {
        g_interface.registerManagedVar(fatCubinHandle, hostVarPtrAddress, deviceAddress, deviceName, ext, size, constant, global);
    }
}

char CUDARTAPI __cudaInitModule(void **fatCubinHandle) {
    Initialize();
    if (g_interface.initModule != NULL) {
        return g_interface.initModule(fatCubinHandle);
    }
    return (char)NULL;
}

void CUDARTAPI __cudaRegisterTexture(
        void                    **fatCubinHandle,
  const struct textureReference  *hostVar,
  const void                    **deviceAddress,
  const char                     *deviceName,
        int                       dim,
        int                       norm,
        int                        ext) {
    Initialize();
    if (g_interface.registerTexture != NULL) {
        g_interface.registerTexture(fatCubinHandle, hostVar, deviceAddress, deviceName, dim, norm, ext);
    }
}

void CUDARTAPI __cudaRegisterSurface(
        void                    **fatCubinHandle,
  const struct surfaceReference  *hostVar,
  const void                    **deviceAddress,
  const char                     *deviceName,
        int                       dim,
        int                       ext) {
    fprintf(stderr, "%s is not supported by HGGC.\n", __func__);
    exit(1);
}

}
