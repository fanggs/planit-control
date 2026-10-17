import {createPreviewServer} from './preview-server.mjs';
const port=Number(process.env.PORT||4174),host=process.env.HOST||'127.0.0.1';
const server=createPreviewServer();
server.on('error',error=>{console.error(error.message);process.exitCode=1;});
server.listen(port,host,()=>console.log(`PlanIT preview: http://${host}:${server.address().port}/ · Supervisor: /supervisor/index.html`));
