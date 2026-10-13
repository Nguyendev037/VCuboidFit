import React, { Suspense } from "react";
import { ContextReview } from "./context-client";
export default function ContextPage() { return <Suspense fallback={<p>Đang tải hàng đợi…</p>}><ContextReview/></Suspense>; }
