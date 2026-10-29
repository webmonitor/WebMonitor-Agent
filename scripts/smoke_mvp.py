"""Real product acceptance. No model, database, browser, or SMTP mocks.

Default: real Agent analysis/extraction/email previews only, never approval.
--send-mail: sends MULTIPLE real change/failure/recovery emails ONLY to MAIL_TEST_TO.
Run through the smoke-runner Docker profile with the smoke overlay and an existing
administrator. The image provides Python, Chromium and Docker Compose.
This script does not use SMTP credentials. Screenshots contain workspace data;
keep them private. The trusted runner's Docker socket grants administrator access.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from decimal import Decimal
from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "http://fixture:8000"
TERMINAL = {"succeeded", "failed", "cancelled", "discarded"}
ACTIVE = {"queued", "running"}


class AcceptanceFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AcceptanceFailure(message)


class Driver:
    def __init__(self, args):
        self.args = args
        self.base = args.base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base, timeout=40, trust_env=False)
        self.groups = []
        self.monitors = []
        self.conversations = []
        self.stamp = uuid4().hex[:10]

    async def compose(self, *arguments, source=None):
        command = ["docker", "compose", "-f", "compose.yaml", "-f", "compose.smoke.yaml", *arguments]
        process = await asyncio.create_subprocess_exec(*command, cwd=ROOT,
            stdin=asyncio.subprocess.PIPE if source is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(source.encode() if source is not None else None), 120)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise AcceptanceFailure("Compose operation exceeded 120 seconds") from None
        require(process.returncode == 0, "Compose operation failed: " + " ".join(arguments[:3])
                + "; inspect service logs (secrets are not printed)")
        return stdout.decode()

    async def fixture(self, **patch):
        # The token never crosses the container boundary and is not printed.
        source = """import json, os, urllib.request
body = json.dumps(PATCH).encode()
request = urllib.request.Request('http://127.0.0.1:8000/_admin/PATH', data=body,
 headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['SMOKE_TOKEN']})
with urllib.request.urlopen(request, timeout=10) as response:
 assert response.status == 200
""".replace("PATCH", repr(patch)).replace("PATH", "state" if patch else "reset")
        await self.compose("exec", "-T", "fixture", "python", "-", source=source)

    async def api(self, method, path, body=None):
        headers = {}
        if method != "GET":
            csrf = await self.client.get("/api/v1/auth/csrf")
            require(csrf.status_code == 200, "CSRF endpoint unavailable")
            headers = {"Origin": self.base, "X-CSRF-Token": csrf.json()["csrf_token"]}
        response = await self.client.request(method, "/api/v1" + path, json=body, headers=headers)
        if not response.is_success:
            try:
                code = response.json()["error"]["code"]
            except (ValueError, KeyError, TypeError):
                code = "non_json_error"
            raise AcceptanceFailure(f"{method} {path}: HTTP {response.status_code} {code}")
        return response.json() if response.content else None

    async def pages(self, path):
        rows, offset = [], 0
        while True:
            separator = "&" if "?" in path else "?"
            page = await self.api("GET", f"{path}{separator}limit=100&offset={offset}")
            rows.extend(page["items"])
            offset += len(page["items"])
            if offset >= page["total"] or not page["items"]:
                return rows

    async def until(self, function, description, timeout=None):
        deadline = time.monotonic() + (timeout or self.args.timeout)
        while time.monotonic() < deadline:
            value = await function()
            if value:
                return value
            await asyncio.sleep(1)
        raise AcceptanceFailure("Timed out: " + description)

    async def ready(self):
        async def check():
            try:
                response = await self.client.get("/api/v1/health/ready")
                return response.status_code == 200
            except httpx.TransportError:
                return False
        await self.until(check, "API/database readiness", 120)

    async def groups_create(self):
        recipient = os.environ.get("MAIL_TEST_TO", "").strip().casefold()
        require(recipient and "," not in recipient and ";" not in recipient and "@" in recipient,
                "MAIL_TEST_TO must be one configured test mailbox, even for recipient previews")
        self.recipient = recipient
        for index in (1, 2):
            group = await self.api("POST", "/notification-groups", {
                "name": f"Smoke {self.stamp} overlap {index}", "enabled": True,
                "members": [{"email": recipient, "active": True}]})
            self.groups.append(group)

    def prompt(self, path, kind):
        groups = ", ".join(group["name"] for group in self.groups)
        common = (f"创建监控 {FIXTURE}{path}，名称 Smoke {self.stamp} {path}。每60秒采集，显示时区 UTC。"
                  f"通知必须选择两个已有组：{groups}（都要选择，不新建或猜测收件人）。"
                  "先实际分析、保存草稿并完成真实提取与邮件预览，再调用 request_creation 等我确认；现在不要创建。")
        if kind == "price":
            return common + ("仅监控当前销售价格 current_price，不是原价；货币USD，金额字段money，"
                             "较上次成功采集下降至少10%才通知，规则number_percent_change/decrease_gte/value=10；"
                             "首次成功只建基线，无通知。静态/SSR页使用HTTP，覆盖full。")
        return common + ("此页通过JavaScript加载列表，使用browser。监控商品列表，业务键为商品id，"
                         "提取id/name/price，仅list_added规则，新加入的商品分别通知。"
                         "等待真实商品行出现后采集；此验收页无分页，请实际核实full覆盖，不设删除规则。")

    async def send(self, cid, text):
        return await self.api("POST", f"/conversations/{cid}/messages",
                              {"content": text, "client_message_id": str(uuid4())})

    async def settled(self, cid):
        async def check():
            snapshot = await self.api("GET", f"/conversations/{cid}")
            runs = [job for job in snapshot["jobs"] if job["kind"] == "agent"]
            require(runs, "Conversation has no agent job")
            run = runs[-1]
            if run["status"] in {"failed", "cancelled"}:
                raise AcceptanceFailure("Real Agent failed: " + str(run["error_code"])
                                        + "; check model/tools; no manual draft fallback")
            return snapshot if run["status"] == "succeeded" else None
        return await self.until(check, "real Agent analysis/preview/confirmation request")

    def draft(self, snapshot):
        return next((draft for draft in snapshot["drafts"]
                     if draft["preview"] is not None), None)

    async def preview(self, cid, kind, path):
        for turn in range(3):
            snapshot = await self.settled(cid)
            draft = self.draft(snapshot)
            if draft is not None:
                break
            if turn == 2:
                raise AcceptanceFailure("Agent needs unresolved clarification after three turns; "
                                        "inspect conversation " + cid)
            # Clarifications remain ordinary real model messages, never server-side specs.
            await self.send(cid, self.prompt(path, kind)
                            + "以上语义已明确，请使用这些信息回答你的澄清并继续真实预览，等待我确认。")
        else:
            raise AcceptanceFailure("No preview was produced")
        preview, spec = draft["preview"], draft["spec"]
        require(draft["monitor_id"] is None, "Monitor existed before approval")
        require(spec["url"] == FIXTURE + path, "Agent changed requested target")
        require(spec["schedule"] == {"interval_seconds": 60, "timezone": "UTC"},
                "Agent changed requested schedule/timezone")
        require(set(spec["notification_group_ids"]) == {g["id"] for g in self.groups},
                "Agent changed notification routing")
        require(spec["collection_mode"] == ("http" if kind == "price" else "browser"),
                "Wrong collection mode")
        require(preview["rendered_emails"] and preview["evidence_refs"],
                "Real email/evidence preview missing")
        require(set(preview["recipients"]) == {self.recipient},
                "Preview recipient not exclusively MAIL_TEST_TO")
        rules = spec["change_rules"]["rules"]
        if kind == "price":
            current_price = next((field for field in spec["fields"]
                                  if field["name"] == "current_price"), None)
            require(current_price and current_price["type"] == "money" and
                    current_price["normalize"]["currency"] == "USD",
                    "Agent changed current-price money/USD semantics")
            require(len(rules) == 1 and rules[0]["type"] == "number_percent_change" and
                    rules[0]["operator"] == "decrease_gte" and
                    Decimal(str(rules[0]["value"])) == 10 and
                    rules[0]["field"] == "current_price", "Agent changed requested price rule")
            require(self.price(preview["extracted_data"]) == 100,
                    "Real current_price preview must be 100")
        else:
            require(len(rules) == 1 and rules[0]["type"] == "list_added",
                    "Agent changed list-added semantics")
            require(spec["business_key"] and preview["coverage"]["scope"] == "full",
                    "List needs proven full coverage and business key")
            require(self.list_keys(spec, preview["extracted_data"]) == {"A"},
                    "Real dynamic preview must contain item A")
        steps = [step["name"] for step in snapshot["jobs"][-1]["steps"]]
        require("request_creation" in steps, "Agent did not request user confirmation")
        return draft

    @staticmethod
    def price(fields):
        price = fields["current_price"]
        return Decimal(str(price["amount"] if isinstance(price, dict) else price))

    @staticmethod
    def list_keys(spec, fields):
        key = spec["business_key"]
        return {str(row[key["item_fields"][0]]) for row in fields[key["field"]]}

    async def create_preview(self, path, kind, page=None):
        if page:
            await page.goto(self.base + "/app")
            await page.locator("#composer").fill(self.prompt(path, kind))
            async with page.expect_response(
                    lambda r: "/messages" in r.url and r.request.method == "POST") as result:
                await page.get_by_role("button", name="发送").click()
            response = await result.value
            require(response.status == 202, "UI message submission failed")
            cid = urlsplit(response.url).path.split("/")[-2]
        else:
            conversation = await self.api("POST", "/conversations",
                                          {"title": f"Smoke {self.stamp} {path}"})
            cid = conversation["id"]
            await self.send(cid, self.prompt(path, kind))
        self.conversations.append(cid)
        draft = await self.preview(cid, kind, path)
        print("PASS real Agent preview: " + path, flush=True)
        return cid, draft

    async def approve(self, cid, draft, page=None):
        body = {"draft_id": draft["id"], "revision": draft["revision"]}
        if page:
            await page.reload()
            async with page.expect_response(
                    lambda response: response.request.method == "POST"
                    and response.url.endswith(f"/conversations/{cid}/approve")) as confirmation:
                await page.get_by_role("button", name="确认创建", exact=True).click(timeout=30000)
            response = await confirmation.value
            require(response.status == 200,
                    "Browser approval request failed: HTTP " + str(response.status))
            monitor = (await response.json())["monitor_id"]
        else:
            monitor = (await self.api("POST", f"/conversations/{cid}/approve", body))["monitor_id"]
        self.monitors.append(monitor)
        for _ in range(2):
            replay = await self.api("POST", f"/conversations/{cid}/approve", body)
            require(replay["monitor_id"] == monitor, "Repeated approval created another monitor")
        rows = [row for row in await self.pages("/monitors") if row["id"] == monitor]
        require(len(rows) == 1, "Approval produced an unexpected monitor count")
        return monitor

    async def events(self, monitor, job_id=None):
        return [event for event in await self.pages("/events")
                if event["monitor_id"] == monitor and (not job_id or event["job_id"] == job_id)]

    async def run(self, monitor, expected="succeeded"):
        queued = await self.api("POST", f"/monitors/{monitor}/run")

        async def check():
            row = await self.api("GET", "/jobs/" + queued["id"])
            return row if row["status"] in TERMINAL else None

        row = await self.until(check, "collection job " + queued["id"])
        require(row["status"] == expected,
                f"Job {row['id']} expected {expected}, got {row['status']} / {row['error_code']}")
        return row

    async def baseline(self, monitor):
        async def check():
            detail = await self.api("GET", "/monitors/" + monitor)
            if detail["health_status"] == "failed":
                raise AcceptanceFailure("First collection failed instead of initializing baseline")
            return detail if detail["baseline_status"] == "ready" else None

        detail = await self.until(check, "first successful scheduled baseline")
        require(not await self.events(monitor), "First successful baseline emitted a business event")
        history = await self.pages(f"/monitors/{monitor}/jobs")
        require(any(row["status"] == "succeeded" for row in history),
                "First baseline was not produced by an actual production job")
        require(detail["baseline"] is not None, "Successful baseline data unavailable")
        if detail["collection_mode"] == "http":
            require(self.price(detail["baseline"]["extracted_data"]) == 100,
                    "First production baseline current_price is not 100")
        return detail

    async def deliveries(self, event, expected="sent"):
        async def check():
            rows = [row for row in await self.pages("/email-deliveries")
                    if row["event_id"] == event["id"]]
            require(len(rows) <= 1, "Overlapping groups produced duplicate delivery")
            for row in rows:
                require(row["recipient"] == self.recipient,
                        "Delivery recipient escaped MAIL_TEST_TO restriction")
                if row["status"] == "failed":
                    raise AcceptanceFailure("Product SMTP delivery failed: " + str(row["error_code"]))
            return rows[0] if rows and rows[0]["status"] == expected else None

        return await self.until(check, "one deduplicated product delivery " + expected)

    async def changed(self, monitor, event_type):
        row = await self.run(monitor)
        events = await self.events(monitor, row["id"])
        require(len(events) == 1 and events[0]["type"] == event_type,
                "Expected exactly one correct change event")
        delivery = await self.deliveries(events[0])
        require(delivery["smtp_response_code"] is not None and
                200 <= delivery["smtp_response_code"] < 300,
                "sent has no SMTP acceptance response")
        return row, events[0], delivery

    async def evidence(self, row):
        snapshot = row["snapshot"]
        require(snapshot and snapshot["evidence_refs"], "Successful job lacks evidence")
        for index, entry in enumerate(snapshot["evidence_refs"]):
            path = f"/api/v1/snapshots/{snapshot['id']}/evidence/{index}"
            authorized = await self.client.get(path)
            require(authorized.status_code == 200, "Authorized evidence unavailable")
            if entry["kind"] == "html":
                require("attachment" in authorized.headers.get("content-disposition", "") and
                        authorized.headers.get("content-type", "").startswith("text/plain"),
                        "HTML evidence can execute same-origin")
            async with httpx.AsyncClient(base_url=self.base, trust_env=False) as anonymous:
                denied = await anonymous.get(path)
                require(denied.status_code == 401, "Unauthenticated evidence not rejected")

    async def security(self):
        source = """import asyncio
from webmonitor.errors import DomainError
from webmonitor.collection.MODE import collect_MODE
async def main():
 for url in TARGETS:
  try:
   await collect_MODE(url)
  except DomainError as error:
   assert error.code == 'url_forbidden', 'Unexpected collection failure: '+error.code
  else:
   raise AssertionError('Private target/resource was not blocked')
 public = await collect_MODE('https://example.com/')
 assert 'Example Domain' in public.html, 'Public HTML could not be collected through egress'
 if 'MODE' == 'browser': assert public.screenshot[:8] == bytes([137,80,78,71,13,10,26,10])
 print('private-targets-blocked')
asyncio.run(main())
"""
        for mode in ("http", "browser"):
            targets = [FIXTURE + "/redirect-private?target=" + target
                       for target in ("loopback", "metadata", "ipv6")]
            targets.extend(["http://127.0.0.1/", "http://169.254.169.254/", "http://[::1]/",
                            "http://10.0.0.1/", "http://postgres/", "http://host.docker.internal/",
                            "http://fixture:8001/", "http://127.0.0.1.nip.io/",
                            "http://169.254.169.254.nip.io/"])
            if mode == "browser":
                targets.append(FIXTURE + "/private-resource")
            result = await self.compose("exec", "-T", "api", "python", "-",
                source=source.replace("MODE", mode).replace("TARGETS", repr(targets)))
            require("private-targets-blocked" in result, "Collector security probe missing proof")
        print("PASS real collector public HTTPS and private IPv4/IPv6/DNS/redirect/subresource "
              "boundaries", flush=True)

    async def screenshots(self, page, cid):
        self.args.screenshots.mkdir(parents=True, exist_ok=True)
        self.args.screenshots.chmod(0o700)
        await page.goto(self.base + "/app")
        await page.get_by_role("link", name="Smoke " + self.stamp, exact=False).first.click(
            timeout=30000)
        await page.get_by_role("button", name="确认创建", exact=True).wait_for(timeout=30000)
        for width in (360, 768, 1440):
            await page.set_viewport_size({"width": width, "height": 900})
            await page.evaluate("document.fonts.ready")
            require(await page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"),
                f"UI horizontal overflow at {width}px")
            destination = self.args.screenshots / f"{self.stamp}-draft-{width}.png"
            await page.screenshot(path=str(destination), full_page=True)
            destination.chmod(0o600)
        print("PASS actual draft confirmation UI at 360/768/1440; private screenshots saved",
              flush=True)

    async def scenario(self, email, password):
        await self.ready()
        await self.fixture()
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(headless=True)
            except Exception:
                raise AcceptanceFailure(
                    "Runner Chromium unavailable; rebuild the smoke-runner image. "
                    "No UI validation was skipped.") from None
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(self.base + "/login")
                await page.get_by_label("邮箱", exact=True).fill(email)
                await page.get_by_label("密码", exact=True).fill(password)
                await page.get_by_label("密码", exact=True).press("Tab")
                await page.keyboard.press("Enter")
                await page.wait_for_url(self.base + "/app", timeout=30000)
                # Transfer the actual browser session, not a second fake/login identity.
                for cookie in await context.cookies():
                    self.client.cookies.set(cookie["name"], cookie["value"])
                profile = await self.api("GET", "/auth/me")
                require(profile["role"] == "admin", "Acceptance requires a real administrator account")
                await self.groups_create()
                cid, draft = await self.create_preview("/static/product", "price", page)
                await self.screenshots(page, cid)
                if self.args.send_mail:
                    monitor = await self.approve(cid, draft, page)
                    await self.baseline(monitor)
                    await self.fixture(current_price="80")
                    row, event, delivery = await self.changed(monitor, "price_changed")
                    require(self.price(event["change"]["before"]) == 100 and
                            self.price(event["change"]["after"]) == 80,
                            "Price event is not 100→80")
                    require("100" in delivery["body_text"] and "80" in delivery["body_text"],
                            "Real delivered body lacks price change")
                    await self.evidence(row)
                    repeat = await self.run(monitor)
                    require(not await self.events(monitor, repeat["id"]),
                            "Same value emitted another event")
                    baseline = (await self.api("GET", "/monitors/" + monitor))["baseline_snapshot_id"]
                    for fault in ("http_500", "empty", "selector_changed"):
                        await self.fixture(**{fault: True})
                        failed = await self.run(monitor, "failed")
                        require((await self.api("GET", "/monitors/" + monitor))["baseline_snapshot_id"]
                                == baseline, "Failure advanced trusted baseline")
                        require(all(event["type"] == "run_failed"
                                    for event in await self.events(monitor, failed["id"])),
                                "Failure emitted business change")
                        await self.fixture(**{fault: False})
                    await self.api("POST", f"/monitors/{monitor}/pause")
                    paused = await self.api("GET", "/monitors/" + monitor)
                    require(paused["status"] == "paused", "Pause did not apply")
                    print("PASS approval replay, scheduled baseline, 100→80, SMTP accepted, "
                          "same-value silence, failure baseline, pause", flush=True)
                await self.fixture()
                for path, kind in (("/ssr/product", "price"), ("/react/list", "list"),
                                   ("/vue/list", "list")):
                    await self.fixture()
                    cid, draft = await self.create_preview(path, kind)
                    if not self.args.send_mail:
                        continue
                    monitor = await self.approve(cid, draft)
                    detail = await self.baseline(monitor)
                    if kind != "list":
                        await self.api("POST", f"/monitors/{monitor}/pause")
                        continue
                    items = [{"id": "A", "name": "Alpha", "price": "10"}]
                    for key in ("B", "C"):
                        items.append({"id": key, "name": "Item " + key, "price": "20"})
                        await self.fixture(items=items)
                        row, event, _ = await self.changed(monitor, "list_changed")
                        require(self.list_keys(detail["spec"], event["change"]["after"]) -
                                self.list_keys(detail["spec"], event["change"]["before"]) == {key},
                                "Consecutive new item event missing/wrong")
                        await self.evidence(row)
                    baseline = (await self.api("GET", "/monitors/" + monitor))["baseline_snapshot_id"]
                    await self.fixture(duplicate=True)
                    await self.run(monitor, "failed")
                    require((await self.api("GET", "/monitors/" + monitor))["baseline_snapshot_id"]
                            == baseline, "Duplicate keys advanced baseline")
                    await self.fixture(duplicate=False)
                    await self.fixture(selector_changed=True)
                    failed = await self.run(monitor, "failed")
                    require(failed["error_code"] == "collection_invalid" and
                            failed["attempt_count"] == 1,
                            "Missing browser selector was incorrectly treated as retryable")
                    require((await self.api("GET", "/monitors/" + monitor))["baseline_snapshot_id"]
                            == baseline, "Missing browser selector advanced baseline")
                    await self.fixture(selector_changed=False)
                    await self.api("POST", f"/monitors/{monitor}/pause")
                await self.security()
                print("PASS full real acceptance; sent means SMTP accepted, not inbox verified"
                      if self.args.send_mail else
                      "PASS real preview-only acceptance; no monitors approved and no "
                      "production mail sent", flush=True)
            finally:
                await browser.close()

    async def close(self):
        # Preserve monitored evidence; stop only work created by this invocation.
        for monitor in self.monitors:
            try:
                await self.api("POST", f"/monitors/{monitor}/pause")
            except Exception:
                print("Cleanup could not pause acceptance monitor " + monitor, file=sys.stderr)
        for cid in self.conversations:
            try:
                snapshot = await self.api("GET", "/conversations/" + cid)
                if any(job["kind"] == "agent" and job["status"] in ACTIVE
                       for job in snapshot["jobs"]):
                    await self.api("POST", f"/conversations/{cid}/cancel")
            except Exception:
                print("Cleanup could not stop acceptance conversation " + cid, file=sys.stderr)
        await self.client.aclose()


async def main(args):
    driver = Driver(args)
    email = input("Existing administrator email: ").strip()
    password = getpass("Administrator password: ")
    try:
        await driver.scenario(email, password)
    finally:
        await driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--send-mail", action="store_true",
        help="Send MULTIPLE real change/failure/recovery emails to MAIL_TEST_TO; "
             "prefer the default preview-only mode first")
    parser.add_argument("--timeout", type=int, default=240,
        help="Bound each Agent/worker/delivery wait in seconds")
    parser.add_argument("--screenshots", type=Path, default=ROOT / ".smoke-artifacts",
        help="Private actual UI screenshots directory")
    arguments = parser.parse_args()
    origin = urlsplit(arguments.base_url)
    require(origin.scheme in {"http", "https"} and origin.hostname and not origin.username and
            origin.path in {"", "/"} and not origin.query and not origin.fragment,
            "--base-url must be an origin without credentials")
    require(arguments.timeout > 0, "--timeout must be positive")
    load_dotenv(ROOT / ".env", override=False)
    try:
        asyncio.run(main(arguments))
    except KeyboardInterrupt:
        print("Acceptance interrupted; no success claimed", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        # Never dump upstream exceptions containing credentials, token-bearing URLs or page data.
        message = (str(error) if isinstance(error, AcceptanceFailure)
                   else type(error).__name__ +
                        "; inspect product logs and dependency/browser availability")
        print("FAIL " + message, file=sys.stderr)
        raise SystemExit(1)
