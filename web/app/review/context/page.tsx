import React, { Suspense } from "react";
import { ContextReview } from "./context-client";
import { LoadingState } from "@/components/ui/DataState";
export default function ContextPage() { return <Suspense fallback={<LoadingState label="Đang tải hàng đợi…" />}><ContextReview/></Suspense>; }
