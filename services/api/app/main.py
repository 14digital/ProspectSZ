from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import router
from app.core.config import get_settings

settings=get_settings(); app=FastAPI(title=settings.app_name,version="1.0.0",docs_url="/api/docs",openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_origin],allow_credentials=True,allow_methods=["GET","POST","PATCH","DELETE"],allow_headers=["Authorization","Content-Type"])
@app.exception_handler(Exception)
async def errors(_:Request,exc:Exception):
    return JSONResponse(status_code=500,content={"code":"INTERNAL_ERROR","message":"Unexpected server error"})
@app.get("/health")
def health(): return {"status":"ok"}
app.include_router(router,prefix="/api/v1")
