import {Maximize, Pause, Play, Volume1, Volume2, VolumeX} from "lucide-react";
import {useEffect, useState, useRef} from "react";
import {useFullscreen} from "@/contexts/FullScreen";
import {cn} from "@/lib/utils";

export default function Qt({infohash, file}: {infohash: string; file: number}) {
    const anchorRef = useRef<HTMLDivElement>(null);
    const [backend, setBackend] = useState<any>(null);
    const {isFullscreen, setFullscreen} = useFullscreen();

    useEffect(() => {
        const win = window as any;
        if (win.QWebChannel && !backend) {
            new win.QWebChannel(win.qt.webChannelTransport, (channel: any) => {
                setBackend(channel.objects.pybridge);
            });
        }
    }, [backend]);

    useEffect(() => {
        if (!backend || !anchorRef.current) return;

        const el = anchorRef.current;
        const syncPosition = () => {
            if (!el || !backend) return;
            const r = el.getBoundingClientRect();
            backend.updateVideoRect(r.left, r.top, r.width, r.height);
        };

        const timer = setTimeout(() => {
            syncPosition();
            backend.start_playback(infohash, file);
        }, 150);

        const observer = new ResizeObserver(syncPosition);
        observer.observe(el);
        window.addEventListener("scroll", syncPosition, true);
        window.addEventListener("resize", syncPosition);

        return () => {
            clearTimeout(timer);
            observer.disconnect();
            window.removeEventListener("scroll", syncPosition, true);
            window.removeEventListener("resize", syncPosition);
            if (backend.stop_playback) {
                backend.stop_playback();
            }
        };
    }, [infohash, file, backend]);

    useEffect(() => {
        const handleResize = () => {
            const isFS = window.innerWidth === window.screen.width && window.innerHeight === window.screen.height;
            setFullscreen(isFS);
        };
        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, []);

    return (
        <div className="h-full flex flex-col">
            <div
                className={
                    isFullscreen
                        ? "fixed inset-0 z-[100000] bg-transparent flex items-center justify-center"
                        : "relative overflow-hidden bg-transparent group flex"
                }>
                {!isFullscreen && <div className="w-4 bg-background shrink-0" />}
                <div
                    ref={anchorRef}
                    className={cn("w-full aspect-video bg-transparent")}
                    style={{
                        borderColor: isFullscreen ? "transparent" : "hsl(var(--background))",
                        boxSizing: "border-box",
                    }}></div>
                {!isFullscreen && <div className="w-4 bg-background shrink-0" />}
                <div className={`absolute inset-0 z-[9999] pointer-events-none py-0
                                 ${isFullscreen ? "" : "p-4"}`}>
                    <div
                        className={`pointer-events-auto h-full w-full relative opacity-80
                                    ${isFullscreen ? "opacity-65" : "opacity-100"}`}>
                        <Controls backend={backend} />
                    </div>
                </div>
            </div>
            {!isFullscreen && <div className="bg-background flex-grow"></div>}
        </div>
    );
}

export function Controls({backend}: any) {
    const {isFullscreen, setFullscreen} = useFullscreen();

    const [progress, setProgress] = useState(0);
    const [isPaused, setIsPaused] = useState(false);
    const [volume, setVolume] = useState(100);
    const [timeStr, setTimeStr] = useState("00:00 / 00:00");
    const [hover, setHover] = useState<{time: string; pos: number} | null>(null);

    const lastVolumeRef = useRef(100);
    const durationRef = useRef(0);

    const formatTime = (s: number) => {
        const date = new Date(s * 1000).toISOString();
        return s >= 3600 ? date.substring(11, 19) : date.substring(14, 19);
    };

    useEffect(() => {
        if (!backend) return;

        const onPosChanged = (curr: number, total: number) => {
            durationRef.current = total;
            if (total > 0) setProgress((curr / total) * 100);
            setTimeStr(`${formatTime(curr)} / ${formatTime(total)}`);
        };

        const onStatusChanged = (paused: boolean) => setIsPaused(paused);
        const onVolumeChanged = (v: number) => setVolume(v);

        backend.position_changed.connect(onPosChanged);
        backend.playback_status.connect(onStatusChanged);
        if (backend.volume_changed) backend.volume_changed.connect(onVolumeChanged);

        return () => {
            backend.position_changed.disconnect(onPosChanged);
            backend.playback_status.disconnect(onStatusChanged);
            if (backend.volume_changed) backend.volume_changed.disconnect(onVolumeChanged);
        };
    }, [backend]);

    return (
        <div
            className={`absolute bottom-0 left-0 right-0 flex flex-col justify-center transition-all
                        duration-300 h-[90px] bg-black p-4 ${isFullscreen ? "opacity-0 hover:opacity-100" : "pb-0"}`}>
            <div className="flex items-center gap-4 w-full mb-2 relative">
                <div
                    className="flex-grow h-1.5 bg-zinc-600 rounded-full cursor-pointer group relative"
                    onMouseMove={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        const percent = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                        setHover({time: formatTime(percent * durationRef.current), pos: percent * 100});
                    }}
                    onMouseLeave={() => setHover(null)}
                    onClick={(e) => {
                        const rect = e.currentTarget.getBoundingClientRect();
                        backend.seek_to(((e.clientX - rect.left) / rect.width) * 100);
                    }}>
                    {hover && (
                        <div
                            className="absolute z-50 text-white bg-zinc-800 px-2 py-0.5 rounded text-[10px] font-mono
                                       border border-gray-600 pointer-events-none whitespace-nowrap ml-4 -translate-y-1/2 top-1/2"
                            style={{left: `${hover.pos}%`}}>
                            {hover.time}
                        </div>
                    )}

                    <div className="h-full bg-tribler rounded-full relative" style={{width: `${progress}%`}}>
                        <div
                            className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full scale-0
                                       group-hover:scale-100 transition-transform"
                        />
                    </div>
                </div>
            </div>

            <div className="flex items-center justify-between w-full">
                <div className="flex items-center gap-6">
                    <button
                        onClick={() => backend.toggle_pause()}
                        className="hover:text-tribler text-white transition-colors">
                        {isPaused ? <Play /> : <Pause />}
                    </button>
                    <div className="flex items-center gap-2 group/vol">
                        <button
                            onClick={() => {
                                if (volume > 0) {
                                    lastVolumeRef.current = volume;
                                    backend.set_volume(0);
                                } else {
                                    backend.set_volume(lastVolumeRef.current || 50);
                                }
                            }}
                            className="hover:text-tribler text-white transition-colors">
                            {volume === 0 ? <VolumeX /> : volume < 50 ? <Volume1 /> : <Volume2 />}
                        </button>
                        <input
                            type="range"
                            min="0"
                            max="100"
                            value={volume}
                            onChange={(e) => {
                                const v = parseFloat(e.target.value);
                                backend.set_volume(v);
                                if (v > 0) lastVolumeRef.current = v;
                            }}
                            className="w-20 h-1 bg-zinc-600 rounded-lg appearance-none cursor-pointer accent-tribler"
                        />
                    </div>
                    <span className="text-sm text-white font-sans tabular-nums whitespace-nowrap min-w-[100px] text-right">
                        {timeStr}
                    </span>
                </div>
                <button
                    onClick={(e) => {
                        const nextState = !isFullscreen;
                        setFullscreen(nextState);
                        if (backend?.toggle_fullscreen) {
                            backend.toggle_fullscreen();
                        }
                    }}
                    className="hover:text-tribler text-white transition-colors p-1">
                    <Maximize />
                </button>
            </div>
        </div>
    );
}
