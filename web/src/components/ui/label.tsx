import * as React from "react";
import {cn} from "@/lib/utils";
export function Label({className,...props}:React.ComponentProps<"label">){return <label className={cn("text-[13px] font-medium leading-none text-ink",className)} {...props}/>}
