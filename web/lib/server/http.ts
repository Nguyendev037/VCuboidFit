/** Phong bì lỗi chuẩn `{error: {code, message}}`; `extra` thêm trường ngang hàng (ví dụ `received`). */
export function errorResponse(
  status: number,
  code: string,
  message: string,
  extra: Record<string, unknown> = {},
): Response {
  return Response.json({ error: { code, message }, ...extra }, { status });
}
