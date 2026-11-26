"""Fast browser preflight against the actual built Vue frontend.

Only API responses are fixtures. This executes the same Python Playwright
functions as real-load; it is not physical storage or backend acceptance.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit

from ci_release_browser import open_admin_storage, measure_storage


class SpaHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path in ("/admin","/login","/fo","/"):
            self.path="/index.html"
        return super().do_GET()


def main():
    from playwright.sync_api import sync_playwright
    dist=Path(sys.argv[1]).resolve()
    assert (dist/"index.html").is_file(),dist
    now="2026-11-26T12:00:00Z"
    usage={
        "disk":{"device":1,"total_bytes":10000000000,"used_bytes":4000000000,
                "available_bytes":6000000000,"reserved_bytes":600000000,"allocatable_bytes":5400000000},
        "registry":{"sampled_at":now,"reconciled_at":now,"partial":False,"stale":False,
                    "errors":0,"missing_expected":0,"pending_changes":0,"cross_owner_inode_conflicts":0,
                    "issues":{},"categories":{},"devices":{},"logical_bytes":0,"allocated_bytes":0},
        "host":None,"filesystems":{}
    }
    password="release_browser_fixture_only"
    logged_in=False
    requests=[]
    unexpected=[]
    def api(route):
        nonlocal logged_in
        request=route.request
        path=urlsplit(request.url).path
        key=(request.method,path)
        requests.append(key)
        if key==("GET","/api/auth/me"):
            if logged_in:route.fulfill(json={"username":"admin"})
            else:route.fulfill(status=401,json={"detail":"Необходим вход"})
        elif key==("POST","/api/auth/login"):
            if request.post_data_json!={"username":"admin","password":password}:
                unexpected.append("incorrect login payload")
                route.fulfill(status=403,json={"detail":"Incorrect fixture login"})
                return
            logged_in=True
            route.fulfill(json={"username":"admin"})
        elif logged_in and key==("GET","/api/activity/own"):
            route.fulfill(json={"account_id":"1","username":"admin","sampled_at":now,"tasks":[]})
        elif logged_in and key==("GET","/api/storage/usage"):
            route.fulfill(json=usage)
        elif logged_in and key==("GET","/api/storage/accounting/issues"):
            route.fulfill(json={"files":[],"missing":[],"offset":0,"limit":50,"snapshot":now})
        else:
            unexpected.append(key)
            route.fulfill(status=404,json={"detail":"Unexpected preflight request"})
    server=ThreadingHTTPServer(("127.0.0.1",0),partial(SpaHandler,directory=str(dist)))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
            try:
                context=browser.new_context()
                context.route("**/api/**",api)
                page=context.new_page()
                errors=[]
                page.on("pageerror",lambda exc:errors.append(str(exc)))
                open_admin_storage(page,base,password)
                page.get_by_text("На этой странице расхождений нет.",exact=True).wait_for(timeout=60000)
                assert ("GET","/api/storage/accounting/issues") in requests
                samples=[measure_storage(page,base) for _ in range(2)]
                assert all(s["browser_storage_seconds"]>0 for s in samples),samples
                assert requests.count(("GET","/api/storage/usage"))>=3,requests
                assert not unexpected,unexpected
                assert not errors,errors
                print("RELEASE_BROWSER_PREFLIGHT_OK",samples,flush=True)
            finally:browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__=="__main__":main()
