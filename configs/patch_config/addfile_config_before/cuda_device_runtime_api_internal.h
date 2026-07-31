#if !defined(__CUDA_DEVICE_RUNTIME_API_INTERNAL_H__)
#define __CUDA_DEVICE_RUNTIME_API_INTERNAL_H__

#ifdef __CUDACC_RDC__
inline __device__  cudaError_t CUDARTAPI __cudaCDP2Malloc(void **p, size_t s)
{
  return cudaErrorUnknown;
}

inline __device__  cudaError_t CUDARTAPI __cudaCDP2FuncGetAttributes(struct cudaFuncAttributes *p, const void *c)
{
  return cudaErrorUnknown;
}

inline __device__  cudaError_t CUDARTAPI __cudaCDP2DeviceGetAttribute(int *value, enum cudaDeviceAttr attr, int device)
{
  return cudaErrorUnknown;
}

inline __device__  cudaError_t CUDARTAPI __cudaCDP2GetDevice(int *device)
{
  return cudaErrorUnknown;
}

inline __device__  cudaError_t CUDARTAPI __cudaCDP2OccupancyMaxActiveBlocksPerMultiprocessor(int *numBlocks, const void *func, int blockSize, size_t dynamicSmemSize)
{
  return cudaErrorUnknown;
}

inline __device__  cudaError_t CUDARTAPI __cudaCDP2OccupancyMaxActiveBlocksPerMultiprocessorWithFlags(int *numBlocks, const void *func, int blockSize, size_t dynamicSmemSize, unsigned int flags)
{
  return cudaErrorUnknown;
}
#endif

inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2DeviceGetCacheConfig(enum cudaFuncCache *pCacheConfig) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2DeviceGetSharedMemConfig(enum cudaSharedMemConfig *pConfig) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2GetLastError(void) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2PeekAtLastError(void) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ const char* CUDARTAPI __cudaCDP2GetErrorString(cudaError_t error) {return "Null";}
inline __device__ __cudart_builtin__ const char* CUDARTAPI __cudaCDP2GetErrorName(cudaError_t error) {return "Null";}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2GetDeviceCount(int *count) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2StreamCreateWithFlags(cudaStream_t *pStream, unsigned int flags) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2StreamDestroy(cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2StreamWaitEvent(cudaStream_t stream, cudaEvent_t event, unsigned int flags) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2StreamWaitEvent_ptsz(cudaStream_t stream, cudaEvent_t event, unsigned int flags) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2EventCreateWithFlags(cudaEvent_t *event, unsigned int flags) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2EventRecord(cudaEvent_t event, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2EventRecord_ptsz(cudaEvent_t event, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2EventRecordWithFlags(cudaEvent_t event, cudaStream_t stream, unsigned int flags) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2EventRecordWithFlags_ptsz(cudaEvent_t event, cudaStream_t stream, unsigned int flags) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2EventDestroy(cudaEvent_t event) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Free(void *devPtr) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2MemcpyAsync(void *dst, const void *src, size_t count, enum cudaMemcpyKind kind, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2MemcpyAsync_ptsz(void *dst, const void *src, size_t count, enum cudaMemcpyKind kind, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Memcpy2DAsync(void *dst, size_t dpitch, const void *src, size_t spitch, size_t width, size_t height, enum cudaMemcpyKind kind, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Memcpy2DAsync_ptsz(void *dst, size_t dpitch, const void *src, size_t spitch, size_t width, size_t height, enum cudaMemcpyKind kind, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Memcpy3DAsync(const struct cudaMemcpy3DParms *p, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Memcpy3DAsync_ptsz(const struct cudaMemcpy3DParms *p, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2MemsetAsync(void *devPtr, int value, size_t count, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2MemsetAsync_ptsz(void *devPtr, int value, size_t count, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Memset2DAsync(void *devPtr, size_t pitch, int value, size_t width, size_t height, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Memset2DAsync_ptsz(void *devPtr, size_t pitch, int value, size_t width, size_t height, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Memset3DAsync(struct cudaPitchedPtr pitchedDevPtr, int value, struct cudaExtent extent, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2Memset3DAsync_ptsz(struct cudaPitchedPtr pitchedDevPtr, int value, struct cudaExtent extent, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2RuntimeGetVersion(int *runtimeVersion) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ void * CUDARTAPI __cudaCDP2GetParameterBuffer(size_t alignment, size_t size) {return nullptr;}
inline __device__ __cudart_builtin__ void * CUDARTAPI __cudaCDP2GetParameterBufferV2(void *func, dim3 gridDimension, dim3 blockDimension, unsigned int sharedMemSize) {return nullptr;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2LaunchDevice_ptsz(void *func, void *parameterBuffer, dim3 gridDimension, dim3 blockDimension, unsigned int sharedMemSize, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2LaunchDeviceV2_ptsz(void *parameterBuffer, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2LaunchDevice(void *func, void *parameterBuffer, dim3 gridDimension, dim3 blockDimension, unsigned int sharedMemSize, cudaStream_t stream) {return cudaErrorUnknown;}
inline __device__ __cudart_builtin__ cudaError_t CUDARTAPI __cudaCDP2LaunchDeviceV2(void *parameterBuffer, cudaStream_t stream) {return cudaErrorUnknown;}

#endif
