import { ApiError, toApiError } from "./api/errors";
export async function fetchExport(url: string): Promise<Blob> {
 let response: Response;
 try { response=await fetch(url); }
 catch { throw new ApiError("network","Không kết nối được worker. Khởi động worker rồi tải lại."); }
 if(!response.ok) throw await toApiError(response);
 return response.blob();
}
