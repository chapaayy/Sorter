"""Shared Chromium scenario for release load and its fast UI preflight."""
import time
from urllib.parse import parse_qs, urlsplit


def open_admin_storage(page, base, password):
    from playwright.sync_api import expect
    response=page.goto(base+"/admin",wait_until="domcontentloaded",timeout=60000)
    assert response and response.status==200,("admin deep link",response.status if response else None)
    page.get_by_label("Электронная почта или логин").fill("admin",timeout=60000)
    assert parse_qs(urlsplit(page.url).query).get("next")==["/admin"],("lost login destination",page.url)
    page.get_by_label("Пароль",exact=True).fill(password)
    page.get_by_role("button",name="Продолжить",exact=True).click()
    page.wait_for_url(base+"/admin",timeout=60000)
    storage=page.get_by_role("region",name="Хранилище",exact=True)
    storage.wait_for(timeout=60000)
    storage.get_by_role("heading",name="Объём хранилища",exact=True).wait_for(timeout=60000)
    toggle=storage.get_by_role("button",name="Диагностика хранилища",exact=True)
    expect(toggle).to_have_attribute("aria-expanded","false",timeout=60000)
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded","true",timeout=60000)
    storage.get_by_role("heading",name="Побайтовый контроль MAP",exact=True).wait_for(timeout=60000)
    storage.get_by_role("heading",name="Сверка и расхождения",exact=True).wait_for(timeout=60000)


def measure_storage(page, base):
    """Retain the original overview-ready latency measurement."""
    start=time.monotonic()
    response=page.goto(base+"/admin",wait_until="domcontentloaded",timeout=60000)
    assert response and response.status==200
    page.get_by_role("region",name="Хранилище",exact=True).get_by_role(
        "heading",name="Объём хранилища",exact=True).wait_for(timeout=60000)
    return {"at":time.time(),"browser_storage_seconds":time.monotonic()-start}
