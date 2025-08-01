import asyncio
import aiohttp
import time

async def test_concurrency(url, total_requests, concurrency):
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    start_time = time.time()
    
    async def fetch(session):
        nonlocal results
        start = time.time()
        try:
            async with semaphore:
                async with session.get(url) as response:
                    elapsed = time.time() - start
                    status = response.status
                    content = await response.text()
                    results.append({
                        "status": status,
                        "time": elapsed,
                        "content_length": len(content)
                    })
                    return status
        except Exception as e:
            elapsed = time.time() - start
            results.append({
                "status": "error",
                "time": elapsed,
                "error": str(e)
            })
            return "error"
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session) for _ in range(total_requests)]
        await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    success_requests = sum(1 for r in results if r["status"] == 200)
    avg_time = sum(r["time"] for r in results) / len(results)
    
    print(f"总耗时: {total_time:.2f}秒")
    print(f"请求总数: {total_requests}")
    print(f"成功请求: {success_requests}")
    print(f"平均响应时间: {avg_time * 1000:.2f}毫秒")
    print(f"吞吐量: {success_requests / total_time:.2f}请求/秒")
    
    return results

# 测试
asyncio.run(test_concurrency("http://192.168.1.101:8501", 100, 20))