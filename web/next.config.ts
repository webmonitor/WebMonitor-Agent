import type {NextConfig} from "next";
const config:NextConfig={output:"standalone",poweredByHeader:false,async rewrites(){const origin=process.env.API_INTERNAL_ORIGIN;return origin?[{source:"/api/v1/:path*",destination:`${origin}/api/v1/:path*`},{source:"/mcp",destination:`${origin}/mcp`},{source:"/mcp/",destination:`${origin}/mcp/`}]:[];}};
export default config;
