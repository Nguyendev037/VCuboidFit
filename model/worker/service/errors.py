"""Phong bì lỗi {"error": {"code", "message"}} — message tiếng Việt cho người dùng."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

HTTP_CODES = {400: "bad_request", 404: "not_found", 409: "busy", 422: "bad_request"}
EXIT_CODES = {2: "contract", 3: "oom", 4: "missing_input"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, e: ApiError):
        return JSONResponse(envelope(e.code, e.message), status_code=e.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        if e.status_code == 404:
            return JSONResponse(envelope("not_found", "Không tìm thấy tài nguyên yêu cầu."), 404)
        code = HTTP_CODES.get(e.status_code, "job_failed")
        return JSONResponse(envelope(code, str(e.detail)), status_code=e.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        first = e.errors()[0] if e.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", [])[1:]) or "dữ liệu gửi lên"
        return JSONResponse(envelope("bad_request", f"Tham số không hợp lệ: {where}."), 400)
