// One loopback-only preview origin serves crew, supervisor, shared styles and
// realtime modules. This keeps the canonical supervisor navigation usable.
import {createPreviewServer} from './preview-server.mjs';

const port=Number(process.env.PORT||4174);
const server=createPreviewServer();
server.on('error',error=>{console.error(error.message);process.exitCode=1;});
server.listen(port,'127.0.0.1',()=>console.log(`ForeSite preview: http://127.0.0.1:${server.address().port}/`));
