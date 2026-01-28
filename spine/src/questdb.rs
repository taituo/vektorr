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
}
