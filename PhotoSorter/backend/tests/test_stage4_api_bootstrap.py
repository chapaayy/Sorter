"""Import the actual ASGI app, not just independent route modules or bytecode."""
from __future__ import annotations

def test_fastapi_all_routers_import_on_fresh_python_interpreter():
    import subprocess
    import sys
    script = """
from server.main import app
from server.main import auth,batches,downloads,site,system
print("ROUTE_DIAGNOSTIC",[(type(r).__name__,getattr(r,'path',None)) for r in app.routes],
      "module_routes", [(m.__name__,len(m.router.routes)) for m in (auth,batches,downloads,site,system)])
routes = {getattr(route,'path',None) for route in app.routes}
for url in ('/', '/v3', '/v3/{path:path}', '/api/health',
            '/api/system/status', '/api/storage/usage', '/api/runs',
            '/api/download/{run_id}', '/api/references/sam/{sam}'):
    assert url in routes, (url, sorted(x for x in routes if isinstance(x,str)))
assert len(routes) >= 30, len(routes)
"""
    result=subprocess.run([sys.executable,"-c",script],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
