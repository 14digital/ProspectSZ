export const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000/api/v1";
export function token(){
 try{return typeof window!=="undefined"?window.localStorage.getItem("prospectsz_token"):null}
 catch{return null}
}
export async function request<T>(path:string,init:RequestInit={}):Promise<T>{
 const headers=new Headers(init.headers); if(!(init.body instanceof FormData))headers.set("Content-Type","application/json"); const t=token(); if(t)headers.set("Authorization",`Bearer ${t}`);
 const response=await fetch(`${API}${path}`,{...init,headers,cache:"no-store"});
 if(!response.ok){let message=`Request failed (${response.status})`;try{const body=await response.json();message=body.detail||body.message||message}catch{}throw new Error(message)}
 if(response.status===204)return undefined as T;
 return response.json()
}
export async function login(email:string,password:string){const body=new URLSearchParams({username:email,password});const response=await fetch(`${API}/auth/token`,{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body});if(!response.ok)throw new Error("Invalid email or password");const data=await response.json();try{window.localStorage.setItem("prospectsz_token",data.access_token)}catch{throw new Error("Browser storage is blocked. Allow site data for localhost and try again.")}}
