"use client";
import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

/** Persist presentation across client navigations of this tab only; explicit present=0 exits.
 * sessionStorage, not localStorage: a sticky flag silently hid the expert panel on later local runs. */
export default function PresentationMode() {
 const params=useSearchParams();
 useEffect(()=>{
  const update=()=>{
   const requested=new URLSearchParams(window.location.search).get("present");
   let enabled=requested==="1";
   try {
    localStorage.removeItem("vcf.present"); // drop the old sticky flag
    if(requested==="1" || requested==="0") sessionStorage.setItem("vcf.present",requested);
    else enabled=sessionStorage.getItem("vcf.present")==="1";
   } catch { enabled=requested==="1"; }
   document.documentElement.dataset.present=enabled ? "1" : "0";
  };
  update(); window.addEventListener("popstate",update); window.addEventListener("storage",update);
  return ()=>{window.removeEventListener("popstate",update);window.removeEventListener("storage",update);};
 },[params]);
 return null;
}
