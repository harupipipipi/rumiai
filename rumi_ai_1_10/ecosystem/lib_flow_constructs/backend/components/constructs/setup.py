"""Flow Constructs Library"""
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import time


def run(context):
    ir = context["interface_registry"]
    src = context.get("_source_component", "lib_flow_constructs:library:constructs")
    
    def loop_construct(kernel, step, ctx):
        exit_when = step.get("exit_when")
        max_iter = step.get("max_iterations", 100)
        for i in range(max_iter):
            if ctx.get("_flow_timeout") or (exit_when and kernel._eval_condition(exit_when, ctx)):
                break
            ctx["_loop_index"] = i
            try:
                asyncio.get_running_loop()
                with ThreadPoolExecutor() as p:
                    ctx = p.submit(asyncio.run, kernel._execute_steps_async(step.get("steps", []), ctx)).result()
            except RuntimeError:
                ctx = asyncio.run(kernel._execute_steps_async(step.get("steps", []), ctx))
        return ctx
    ir.register("flow.construct.loop", loop_construct, meta={"_source_component": src})
    
    def branch_construct(kernel, step, ctx):
        cond = step.get("condition")
        steps = step.get("then", []) if cond and kernel._eval_condition(cond, ctx) else step.get("else", [])
        try:
            asyncio.get_running_loop()
            with ThreadPoolExecutor() as p:
                ctx = p.submit(asyncio.run, kernel._execute_steps_async(steps, ctx)).result()
        except RuntimeError:
            ctx = asyncio.run(kernel._execute_steps_async(steps, ctx))
        return ctx
    ir.register("flow.construct.branch", branch_construct, meta={"_source_component": src})
    
    def parallel_construct(kernel, step, ctx):
        branches = step.get("branches", [])
        results = {}
        with ThreadPoolExecutor(max_workers=max(len(branches), 1)) as ex:
            futs = {}
            for i, b in enumerate(branches):
                def run_branch(s, c):
                    return asyncio.run(kernel._execute_steps_async(s, c))
                future = ex.submit(run_branch, b.get("steps", []), copy.deepcopy(ctx))
                futs[future] = b.get("name", f"b{i}")
            for f in as_completed(futs):
                try:
                    results[futs[f]] = f.result()
                except Exception as e:
                    results[futs[f]] = {"_error": str(e)}
        ctx["_parallel_results"] = results
        return ctx
    ir.register("flow.construct.parallel", parallel_construct, meta={"_source_component": src})
    
    def group_construct(kernel, step, ctx):
        if step.get("when") and not kernel._eval_condition(step["when"], ctx):
            return ctx
        try:
            asyncio.get_running_loop()
            with ThreadPoolExecutor() as p:
                ctx = p.submit(asyncio.run, kernel._execute_steps_async(step.get("steps", []), ctx)).result()
        except RuntimeError:
            ctx = asyncio.run(kernel._execute_steps_async(step.get("steps", []), ctx))
        return ctx
    ir.register("flow.construct.group", group_construct, meta={"_source_component": src})
    
    def retry_construct(kernel, step, ctx):
        handler = kernel.interface_registry.get(step.get("handler"))
        if not handler or not callable(handler):
            return ctx
        for attempt in range(step.get("max_attempts", 3)):
            try:
                args = kernel._resolve_value(step.get("args", {}), ctx)
                result = asyncio.run(handler(args, ctx)) if asyncio.iscoroutinefunction(handler) else handler(args, ctx)
                if step.get("output"):
                    ctx[step["output"]] = result
                return ctx
            except Exception as e:
                if attempt < step.get("max_attempts", 3) - 1 and step.get("delay_ms", 0) > 0:
                    time.sleep(step["delay_ms"] / 1000)
                ctx["_retry_error"] = str(e)
        return ctx
    ir.register("flow.construct.retry", retry_construct, meta={"_source_component": src})
