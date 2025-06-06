# Copyright (c) 2025, Alibaba Group;
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#    http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import gc
import unittest
from typing import Optional

import torch
from hypothesis import Verbosity, given
from hypothesis import strategies as st

from tzrec.ops import Kernel
from tzrec.utils.test_util import get_test_dtypes, gpu_unavailable
from tzrec.utils.test_util import hypothesis_settings as settings


class MMlTest(unittest.TestCase):
    def teardown_example(self, example):
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.memory_summary()  # prevent oom

    @unittest.skipIf(*gpu_unavailable)
    # pyre-ignore[56]
    @given(
        M=st.integers(min_value=100, max_value=300),
        N=st.integers(min_value=100, max_value=300),
        K=st.integers(min_value=100, max_value=300),
        broadcast=st.booleans(),
        dtype=st.sampled_from(
            get_test_dtypes([torch.float32, torch.bfloat16, torch.float16])
        ),
    )
    @settings(
        verbosity=Verbosity.verbose,
        max_examples=20,
        deadline=None,
    )
    def test_addmm(
        self,
        M: int,
        N: int,
        K: int,
        broadcast: bool,
        dtype: torch.dtype,
    ) -> None:
        self._test_addmm(
            M=M,
            N=N,
            K=K,
            broadcast=broadcast,
            dtype=dtype,
            kernel_type=Kernel.TRITON,
        )

    def _test_addmm(
        self,
        M: int,
        N: int,
        K: int,
        broadcast: bool,
        dtype: torch.dtype,
        kernel_type: Kernel,
        atol: Optional[float] = None,
        rtol: Optional[float] = None,
    ) -> None:
        from tzrec.ops.mm import addmm

        # to enable more deterministic results.
        torch.manual_seed(0)

        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False

        x: torch.Tensor = torch.rand((M, K), dtype=dtype, device="cuda").requires_grad_(
            True
        )
        w: torch.Tensor = torch.rand((K, N), dtype=dtype, device="cuda").requires_grad_(
            True
        )

        if broadcast:
            y: torch.Tensor = torch.rand(
                (N), dtype=dtype, device="cuda"
            ).requires_grad_(True)
        else:
            y: torch.Tensor = torch.rand(
                (M, N), dtype=dtype, device="cuda"
            ).requires_grad_(True)

        ref_z = addmm(y, x, w, kernel=Kernel.PYTORCH)
        dz = torch.randn_like(ref_z) * 0.1
        ref_z.backward(dz)
        # pyre-ignore[16]
        ref_dx, x.grad = x.grad.detach().clone(), None
        ref_dw, w.grad = w.grad.detach().clone(), None
        ref_dy, y.grad = y.grad.detach().clone(), None

        x = x.detach().clone().requires_grad_(True)
        w = w.detach().clone().requires_grad_(True)
        y = y.detach().clone().requires_grad_(True)
        real_z = addmm(y, x, w, kernel=kernel_type)

        torch.testing.assert_close(ref_z, real_z, atol=atol, rtol=rtol)

        real_z.backward(dz)
        real_dx, x.grad = x.grad.detach().clone(), None
        real_dw, w.grad = w.grad.detach().clone(), None
        real_dy, y.grad = y.grad.detach().clone(), None

        torch.testing.assert_close(ref_dx, real_dx, atol=atol, rtol=rtol)
        torch.testing.assert_close(ref_dw, real_dw, atol=atol, rtol=rtol)
        torch.testing.assert_close(ref_dy, real_dy, atol=atol, rtol=rtol)


if __name__ == "__main__":
    unittest.main()
