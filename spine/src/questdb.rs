use anyhow::Result;
use tokio::io::AsyncWriteExt;
use tokio::net::TcpStream;

pub struct QuestDbClient {
    stream: TcpStream,
}

impl QuestDbClient {
    pub async fn connect(host: &str, port: u16) -> Result<Self> {
        let addr = format!("{}:{}", host, port);
        let stream = TcpStream::connect(addr).await?;
        Ok(Self { stream })
    }

    pub async fn write_line(&mut self, line: &str) -> Result<()> {
        self.stream.write_all(line.as_bytes()).await?;
        self.stream.write_all(b"\n").await?;
        Ok(())
    }

    pub async fn write_lines(&mut self, lines: &[String]) -> Result<()> {
        if lines.is_empty() {
            return Ok(());
        }
        let mut buf = String::new();
        for (idx, line) in lines.iter().enumerate() {
            if idx > 0 {
                buf.push('\n');
            }
            buf.push_str(line);
        }
        buf.push('\n');
        self.stream.write_all(buf.as_bytes()).await?;
        Ok(())
    }
}
