import {useEffect, useState} from "react";
import {triblerService} from "@/services/tribler.service";
import {Button} from "@/components/ui/button";

export default function MPVPlaceHolder({infohash, file}: {infohash: string; file: number}) {
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        (async () => {
            setError(null);
            const result = await triblerService.playVideo(infohash, file);

            if (result && result.status === "error") {
                setError(result.message || "Failed to start MPV player.");
            }
        })();

        return () => {
        };
    }, [infohash, file]);

    return (
        <div className="relative overflow-hidden bg-background rounded-lg flex flex-col items-center justify-center aspect-video w-full">
            <div className="text-center p-6 select-none">
                <div className="flex justify-center mb-3">
                    <div
                        className={
                            error
                                ? "h-2 w-2 rounded-full bg-red-500 animate-pulse"
                                : "h-2 w-2 rounded-full bg-green-500 animate-pulse"
                        }
                    />
                </div>

                <p className="text-sm font-medium">{error ? "Player Error" : "Playing in External Window"}</p>

                <p className="text-xs text-muted-foreground mt-1 max-w-xs mx-auto">
                    {error ? error : "Control playback directly inside the native MPV popup window."}
                </p>

                {!error && (
                    <Button
                        variant="outline"
                        type="submit"
                        onClick={() => triblerService.shutdownVideo()}
                        className="mt-4 px-3 py-1.5 text-xs font-medium hover:text-red-400 hover:border-red-400 transition-colors">
                        Stop Playback
                    </Button>
                )}
            </div>
        </div>
    );
}
