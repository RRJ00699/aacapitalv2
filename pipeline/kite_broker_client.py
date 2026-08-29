"""Credential-free VM client for the protected Cloudflare Kite broker Worker."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class KiteBrokerError(RuntimeError):
    pass


@dataclass(frozen=True)
class KiteBrokerClient:
    base_url: str
    secret: str
    timeout: int = 30

    @classmethod
    def from_env(cls):
        url=(os.environ.get("KITE_BROKER_PROXY_URL") or "").strip().rstrip("/")
        secret=(os.environ.get("KITE_BROKER_PROXY_AUTH_SECRET") or "").strip()
        if not url or not secret:
            raise KiteBrokerError("KITE_BROKER_PROXY_URL and KITE_BROKER_PROXY_AUTH_SECRET are required")
        return cls(url,secret)

    def _post(self,path:str,payload:dict[str,Any],retries:int=2):
        raw=json.dumps(payload,separators=(",",":"),default=str).encode()
        req=urllib.request.Request(self.base_url+path,data=raw,method="POST",headers={
            "content-type":"application/json","authorization":f"Bearer {self.secret}",
            "user-agent":"aacapital-pipeline/1","accept":"application/json"})
        last=None
        for attempt in range(retries+1):
            try:
                with urllib.request.urlopen(req,timeout=self.timeout) as res: out=json.load(res)
                if not isinstance(out,dict) or out.get("ok") is False:
                    raise KiteBrokerError(str((out or {}).get("error") or "broker rejected request"))
                return out
            except urllib.error.HTTPError as exc:
                body=exc.read().decode(errors="replace")
                if 400<=exc.code<500:
                    try: detail=json.loads(body).get("error")
                    except Exception: detail=body[:300]
                    raise KiteBrokerError(f"broker HTTP {exc.code}: {detail}") from None
                last=exc
            except (urllib.error.URLError,TimeoutError,OSError,json.JSONDecodeError) as exc: last=exc
            if attempt<retries: time.sleep(2**attempt)
        raise KiteBrokerError(f"broker unavailable: {type(last).__name__}: {last}")

    def quotes(self,symbols:list[str],allowed_symbols:list[str]):
        return self._post("/quotes",{"symbols":symbols,"allowed_symbols":allowed_symbols}).get("quotes") or {}

    def historical(self,*,symbol:str,allowed_symbols:list[str],from_date:str,to_date:str,interval:str):
        return self._post("/historical",{"symbol":symbol,"allowed_symbols":allowed_symbols,
            "from":from_date,"to":to_date,"interval":interval}).get("candles") or []
