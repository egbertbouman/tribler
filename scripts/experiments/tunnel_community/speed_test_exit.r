library(ggplot2)
library(reshape2)
library(patchwork)

speeds <- read.table("speed_test_exit.txt", header=T, quote="\"")
speeds <- speeds[c(1:3)]
speeds <- melt(speeds , id.vars = 'Time', variable.name = 'Direction')
speeds_plot <- ggplot(speeds, aes(Time, value)) +
  geom_line(aes(colour = Direction), alpha = 0.25) +
  geom_smooth(aes(colour = Direction), se = FALSE) +
  ggtitle("Throughput") +
  ylab("Throughput (MB/s)") +
  xlab("Time (s)") +
  expand_limits(x = 0) +
  scale_x_continuous(expand = c(0, 0))

rtts <- read.table("speed_test_exit_rtt.txt", header=T, quote="\"")
rtts_plot <- ggplot(subset(rtts, !is.na(rtts$RTT)), aes(Time, RTT)) +
  geom_vline(data=rtts[is.na(rtts$RTT),], aes(xintercept=Time), colour = 6, alpha = 0.1, linewidth = min(c(40000/nrow(rtts), 1))) +
  geom_line(color = '#B9D6EA') +
  geom_smooth(color = 4, se = FALSE) +
  ggtitle("Round-Trip Time") +
  ylab("RTT (ms)") +
  xlab("Time (s)") +
  expand_limits(x = 0) +
  scale_x_continuous(expand = c(0, 0))

p <- speeds_plot / rtts_plot
ggsave("speed_test_exit.png", p, width=10, height=10, dpi=300)
q(save="no")
