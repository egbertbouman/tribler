import {useEffect, useRef} from "react";
import videojs from "video.js";
import "video.js/dist/video-js.css";

export function VideoJS({infohash, file}: {infohash: string; file: number}) {
    const videoRef = useRef<HTMLDivElement>(null);
    const playerRef = useRef<any>(null);

    const videoUrl = `/api/downloads/${infohash}/stream/${file}`;

    useEffect(() => {
        // Make sure Video.js player is only initialized once
        if (!playerRef.current && videoRef.current) {
            const videoElement = document.createElement("video-js");
            videoElement.classList.add("vjs-big-play-centered");
            videoRef.current.appendChild(videoElement);

            const player = (playerRef.current = videojs(
                videoElement,
                {
                    autoplay: true,
                    controls: true,
                    responsive: true,
                    fluid: true,
                    sources: [{src: videoUrl, type: "video/mp4"}],
                },
                () => {
                    console.log("VideoJS player is ready");
                }
            ));
        }
        // The player already exists. Update the source.
        else if (playerRef.current) {
            const player = playerRef.current;
            player.src({src: videoUrl, type: "video/mp4"});
        }

        // Destroy the player when the component unmounts, or HTTP connections will remain open.
        // This prevents videofiles from being locked.
        return () => {
            if (playerRef.current && !playerRef.current.isDisposed()) {
                playerRef.current.dispose();
                playerRef.current = null;
            }
        };
    }, [infohash, file]);

    return (
        <div data-vjs-player className="bg-background w-full h-full p-4 pt-0">
            <div ref={videoRef} />
        </div>
    );
}
