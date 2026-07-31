#if !defined(__CUDA_RUNTIME_API_EXT_H__)
#define __CUDA_RUNTIME_API_EXT_H__

enum __device_builtin__ cudaFuncAttributeExt
{
    cudaFuncAttributeExtDispatchStrategy = 0, /**< Dispatch Strategy */
    cudaFuncAttributeExtBlockAgeEn = 1, /* block age priority when scheduling warps*/
    cudaFuncAttributeExtDispatchMask = 2, /* Dispatch mask*/
    cudaFuncAttributeExtMax
};


extern __host__ __cudart_builtin__ cudaError_t CUDARTAPI cudaFuncSetAttributeExt(const void *func, enum cudaFuncAttributeExt attr, int value);

#ifdef __cplusplus
template<class T>
static __inline__ __host__ cudaError_t cudaFuncSetAttributeExt(
  T                         *entry,
  enum cudaFuncAttributeExt    attr,
  int                       value
)
{
  return ::cudaFuncSetAttributeExt((const void*)entry, attr, value);
}
#endif

#endif // __CUDA_RUNTIME_API_EXT_H__
