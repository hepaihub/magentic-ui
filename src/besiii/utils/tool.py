import time
from typing import Callable, Coroutine, Any

@staticmethod
def timed_method(func: Callable[..., Coroutine[Any, Any, Any]]):
    """异步方法专用计时装饰器"""
    async def async_wrapper(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            result = await func(self, *args, **kwargs)
            elapsed = time.perf_counter() - start
            print(f"\033[30mConsume {elapsed:.2f}s\033[0m")
            return result
        finally:
            # 确保即使出错也记录时间
            elapsed = time.perf_counter() - start
            if elapsed < 0.0001:
                print("⚠️ 检测到异常计时，可能未正确await异步操作")
    return async_wrapper