"use client";
import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

/** Persist presentation across client navigations; explicit present=0 exits. */
export default function PresentationMode() {
 const params=useSearchParams();
 useEffect(()=>{
  const update=()=>{
   const requested=new URLSearchParams(window.location.search).get("present");
   let enabled=requested==="1";
   try {
    if(requested==="1" || requested==="0") localStorage.setItem("vcf.present",requested);
    else enabled=localStorage.getItem("vcf.present")==="1";
   } catch { enabled=requested==="1"; }
   document.documentElement.dataset.present=enabled ? "1" : "0";
  };
  update(); window.addEventListener("popstate",update); window.addEventListener("storage",update);
  return ()=>{window.removeEventListener("popstate",update);window.removeEventListener("storage",update);};
 },[params]);
 return <div data-presentation-banner role="status" className="border-b border-vcf-border bg-vcf-accent-soft px-4 py-2 text-center font-semibold text-vcf-accent-ink">Demo · dữ liệu nuScenes</div>;
}
