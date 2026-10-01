#*************************************************************************
# SPDX-FileCopyrightText: Copyright (c) 2022-2026 T-Head (Shanghai) Semiconductor Co., Ltd. All rights reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
# See LICENSE.txt for more license information
#*************************************************************************

PCCL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null && pwd)"

echo "Setup NCCL wrapper environment for Release"
export PCCL_HOME=$PCCL_ROOT
export NCCL_HOME=$PCCL_ROOT/nccl_wrapper
export PATH=$PCCL_HOME/bin:$PATH
export LD_LIBRARY_PATH=$NCCL_HOME/lib:$PCCL_HOME/lib:${LD_LIBRARY_PATH}
export LIBRARY_PATH=$NCCL_HOME/lib:${LIBRARY_PATH}
