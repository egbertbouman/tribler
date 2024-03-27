library(ggplot2)
library(reshape2)

popularity <- read.table("torrent_collecting.txt", header=T, quote="\"")
popularity <- popularity[c(1:4)]
popularity <- melt(popularity , id.vars = 'Time', variable.name = 'Items')
p <- ggplot(popularity, aes(Time, value)) +
  geom_area(aes(colour=Items, fill=Items)) +
  ggtitle("Number of torrents collected") +
  ylab("Torrents") +
  xlab("Time (s)") +
  scale_fill_brewer(palette="RdYlBu") +
  scale_colour_brewer(palette="RdYlBu") +
  theme(legend.title=element_blank())
p
ggsave("torrent_collecting.png", width=10, height=6, dpi=100)
q(save="no")
