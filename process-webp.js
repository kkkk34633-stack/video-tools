// process-webp.js
import { createClient } from '@supabase/supabase-js';
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { exec } from 'child_process';
import util from 'util';
import fs from 'fs';
import path from 'path';
const execPromise = util.promisify(exec);

// ==========================================
// 1. Supabase 配置
// ==========================================
const SUPABASE_URL = "https://etietwvnqxlcvghyasxw.supabase.co";
const SUPABASE_KEY = "sb_publishable_l3yKmjHJ9IgpbcUgcakvkA_yvvY5NHu";
const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

// ==========================================
// 2. Cloudflare R2 配置（请替换为你自己的凭证）
// ==========================================
const R2_ACCOUNT_ID = 'b257ddf9f8d76c000787b5bae86a07c2'; // 在 R2 页面右侧面板可以找到
const R2_ACCESS_KEY_ID = '54235d87b340dbdd438e828c4e1f30e5';
const R2_SECRET_ACCESS_KEY = '85d0e16fd137cb69e34e21dc9c722f6ee9a9b43ff8fee82a88f35b2de855933d';
const R2_BUCKET_NAME = 'my-video-bucket'; // 例如：my-video-bucket

const CDN_BASE_URL = 'https://pub-452a8da165414920b25c762236914e47.r2.dev/';

// 初始化 R2 (S3 兼容) 客户端
const r2Client = new S3Client({
  region: 'auto',
  endpoint: `https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: R2_ACCESS_KEY_ID,
    secretAccessKey: R2_SECRET_ACCESS_KEY,
  },
});

// 封装 R2 上传函数
async function uploadToR2(localFilePath, r2Key) {
  const fileStream = fs.createReadStream(localFilePath);
  const command = new PutObjectCommand({
    Bucket: R2_BUCKET_NAME,
    Key: r2Key,
    Body: fileStream,
    ContentType: 'image/webp',
  });
  await r2Client.send(command);
}

// ==========================================
// 3. 主执行逻辑
// ==========================================
async function startWorker() {
  console.log("🤖 WebP 转换脚本已启动，准备开始批量处理新视频...");

  if (!fs.existsSync('./temp')) {
    fs.mkdirSync('./temp');
  }

  const { data: pendingVideos, error } = await supabase
    .from('videos')
    .select('id, slug, m3u8_url')
    .eq('webp_status', 'pending');

  if (error) {
    console.error('❌ 获取待处理视频失败:', error.message);
    process.exit(1);
  }

  if (!pendingVideos || pendingVideos.length === 0) {
    console.log('🎉 没有检测到需要处理的新视频！脚本直接退出。');
    process.exit(0);
  }

  console.log(`📦 本次共检测到 ${pendingVideos.length} 个新视频待处理，开始逐一转换...\n`);

  for (let i = 0; i < pendingVideos.length; i++) {
    const video = pendingVideos[i];
    const progressText = `[${i + 1}/${pendingVideos.length}]`;

    try {
      await supabase.from('videos').update({ webp_status: 'processing' }).eq('id', video.id);
      console.log(`🎬 ${progressText} 开始处理视频 [${video.slug}]...`);

      const fullM3u8Url = video.m3u8_url.startsWith('http') ? video.m3u8_url : `${CDN_BASE_URL}${video.m3u8_url}`;
      
      const localWebpPath = `./temp/${video.slug}.webp`;

      // 提取 R2 Key
      let relativeM3u8Path = video.m3u8_url;
      if (relativeM3u8Path.startsWith(CDN_BASE_URL)) {
        relativeM3u8Path = relativeM3u8Path.replace(CDN_BASE_URL, '');
      }
      
      const parentDir = path.dirname(relativeM3u8Path); 
      const r2ObjectKey = `${parentDir}/preview.webp`; 

      // 🎬 方案：精准截取 3 个不同时间段，拼成 20 秒的分散预览图
      // 第 1 段：00:00:10 截取 7 秒
      // 第 2 段：00:02:00 截取 7 秒
      // 第 3 段：00:05:00 截取 6 秒
      // 总时长：7s + 7s + 6s = 20 秒
      const ffmpegCmd = `ffmpeg -y -i "${fullM3u8Url}" -filter_complex "[0:v]trim=start=10:end=17,setpts=PTS-STARTPTS[v1]; [0:v]trim=start=120:end=127,setpts=PTS-STARTPTS[v2]; [0:v]trim=start=300:end=306,setpts=PTS-STARTPTS[v3]; [v1][v2][v3]concat=n=3:v=1:a=0[v0]; [v0]fps=6,scale=360:-1:flags=lanczos[out]" -map "[out]" -vcodec libwebp -lossless 0 -compression_level 5 -q:v 35 -loop 0 "${localWebpPath}"`;
      await execPromise(ffmpegCmd);

      // 2. 🌟 真正的 R2 上传逻辑
      console.log(`⬆️ ${progressText} 正在上传文件至 R2: ${r2ObjectKey}`);
      await uploadToR2(localWebpPath, r2ObjectKey);

      // 3. 上传成功后更新数据库状态
      await supabase.from('videos').update({ webp_status: 'success' }).eq('id', video.id);
      console.log(`✅ ${progressText} 成功: [${r2ObjectKey}] 已同步至 R2 同级目录！`);

      // 4. 清理本地临时文件
      if (fs.existsSync(localWebpPath)) {
        fs.unlinkSync(localWebpPath);
      }

    } catch (err) {
      console.error(`❌ ${progressText} 视频 [${video.slug}] 处理出错:`, err.message);
      await supabase.from('videos').update({ webp_status: 'failed' }).eq('id', video.id);
    }
  }

  console.log("\n🎉 所有待处理视频的 WebP 均已制作并上传完毕！脚本任务圆满完成。");
  process.exit(0);
}

startWorker();