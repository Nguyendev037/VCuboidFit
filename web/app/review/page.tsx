import { redirect } from "next/navigation";

export default function ReviewRootPage() {
  redirect("/review/mock-job?sel=sel-balanced&budget=0.05");
}
