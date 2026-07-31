#ifndef __CUSOLVER_NOHEADER_API__
#define __CUSOLVER_NOHEADER_API__

extern "C" cusolverStatus_t cusolverDnSgemmHost(cublasOperation_t transa,
                                                cublasOperation_t transb,
                                                int m,
                                                int n,
                                                int k,
                                                const float* alpha,
                                                const float* A,
                                                int lda,
                                                const float* B,
                                                int ldb,
                                                const float* beta,
                                                float* C,
                                                int ldc);

extern "C" cusolverStatus_t cusolverDnDgemmHost(cublasOperation_t transa,
                                                cublasOperation_t transb,
                                                int m,
                                                int n,
                                                int k,
                                                const double* alpha,
                                                const double* A,
                                                int lda,
                                                const double* B,
                                                int ldb,
                                                const double* beta,
                                                double* C,
                                                int ldc);

extern "C" cusolverStatus_t cusolverDnSsterfHost(int n, float* d, float* e, int* info);

extern "C" cusolverStatus_t cusolverDnDsterfHost(int n, double* d, double* e, int* info);

extern "C" cusolverStatus_t cusolverDnSsteqrHost(
  const signed char* compz, int n, float* d, float* e, float* z, int ldz, float* work, int* info);

extern "C" cusolverStatus_t cusolverDnDsteqrHost(const signed char* compz,
                                                 int n,
                                                 double* d,
                                                 double* e,
                                                 double* z,
                                                 int ldz,
                                                 double* work,
                                                 int* info);

#endif //__CUSOLVER_NOHEADER_API__
