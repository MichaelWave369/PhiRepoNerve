"""GitHub GET-only inventory client. Pagination and identity are explicit."""

import json
import os
import re
from urllib import error, parse, request


class InventoryError(RuntimeError):
    """An inventory cannot be represented as complete."""


class GitHubClient:
    API = "https://api.github.com"

    def __init__(self, token=None, opener=None, timeout=20):
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        self.opener = opener or request.urlopen
        self.timeout = timeout

    def _get_page(self, url):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "PhiRepoNerve/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        req = request.Request(url, headers=headers, method="GET")
        try:
            with self.opener(req, timeout=self.timeout) as res:
                if res.status != 200:
                    raise InventoryError("GitHub returned HTTP " + str(res.status))
                data = json.load(res)
                link = res.headers.get("Link", "")
        except error.HTTPError as exc:
            raise InventoryError("GitHub returned HTTP " + str(exc.code)) from None
        except (error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise InventoryError("GitHub inventory request failed: " + type(exc).__name__) from None
        if not isinstance(data, list):
            raise InventoryError("GitHub inventory response was not a repository list")
        return data, link

    @staticmethod
    def _next_link(link):
        for part in link.split(","):
            if re.search(r'rel=["\']?next["\']?', part):
                match = re.search(r"<([^>]+)>", part)
                if match:
                    return match.group(1)
        return None

    @staticmethod
    def _normalize(item, owner):
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            raise InventoryError("Repository response lacks a stable numeric ID")
        actual_owner = ((item.get("owner") or {}).get("login") or "").casefold()
        name = item.get("full_name")
        if actual_owner != owner.casefold() or not isinstance(name, str) or not name:
            raise InventoryError("Repository response owner/name does not match requested owner")
        return {
            "github_id": item["id"],
            "full_name": name,
            "private": bool(item.get("private", False)),
            "archived": bool(item.get("archived", False)),
            "default_branch": item.get("default_branch") or "",
            "pushed_at": item.get("pushed_at") or "",
            "description": (item.get("description") or "")[:1000],
            "html_url": item.get("html_url") or ("https://github.com/" + name),
        }

    def inventory(self, owner, max_pages=1000):
        if not owner or not re.fullmatch(r"[a-zA-Z0-9-]{1,39}", owner):
            raise ValueError("Invalid GitHub account login")
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        # User token: owner-affiliated inventory, including accessible private repos.
        # Anonymous: documented public-only GitHub endpoint.
        path = "/user/repos" if self.token else "/users/" + owner + "/repos"
        params = {
            "per_page": "100",
            "page": "1",
        }
        if self.token:
            params.update({"affiliation": "owner", "sort": "full_name", "direction": "asc"})
        else:
            params.update({"type": "owner", "sort": "full_name", "direction": "asc"})
        url = self.API + path + "?" + parse.urlencode(params)
        seen_pages, found = set(), {}
        page = 1
        while url:
            if page > max_pages or url in seen_pages:
                raise InventoryError("Inventory pagination was cyclic or exceeded its limit")
            parsed = parse.urlparse(url)
            if parsed.scheme != "https" or parsed.netloc != "api.github.com" or parsed.path != path:
                raise InventoryError("Unsafe pagination link from GitHub")
            seen_pages.add(url)
            batch, link = self._get_page(url)
            for item in batch:
                row = self._normalize(item, owner)
                if row["github_id"] in found:
                    raise InventoryError("Duplicate repository ID across pages; inventory changed during scan")
                found[row["github_id"]] = row
            next_url = self._next_link(link)
            if next_url:
                url = next_url
            elif len(batch) == 100:
                # If Link was stripped by a proxy, probe until a short/empty page.
                page_args = parse.parse_qs(parsed.query)
                page_args["page"] = [str(int(page_args.get("page", ["1"])[0]) + 1)]
                url = self.API + path + "?" + parse.urlencode(page_args, doseq=True)
            else:
                url = None
            page += 1
        return sorted(found.values(), key=lambda row: row["full_name"].casefold())
