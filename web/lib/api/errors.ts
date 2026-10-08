/** Lỗi API chuẩn: `{error: {code, message}}`; `message` là câu tiếng Việt cho người dùng. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export function genericMessage(status: number): string {
  if (status === 401) return "Bạn chưa đăng nhập hoặc phiên đã hết hạn.";
  if (status === 404) return "Không tìm thấy tài nguyên được yêu cầu.";
  if (status === 413) return "Dữ liệu gửi lên quá lớn.";
  if (status >= 500) return "Máy chủ gặp sự cố. Hãy thử lại sau ít phút.";
  return "Yêu cầu không thành công. Hãy thử lại.";
}

/** Đọc phong bì lỗi; không phải phong bì thì trả mã `http_<status>`. */
export async function toApiError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const e = body?.error;
    if (e && typeof e.code === "string" && typeof e.message === "string") {
      return new ApiError(e.code, e.message, res.status);
    }
  } catch {
    // thân không phải JSON (ví dụ HTML 502 của proxy)
  }
  return new ApiError(`http_${res.status}`, genericMessage(res.status), res.status);
}
