import {useLocation, useNavigate, useParams} from "react-router-dom";
import {useEffect, useState} from "react";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";
import {Button} from "@/components/ui/button";
import {Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList} from "@/components/ui/command";
import {Check, ChevronLeft, ChevronsUpDown} from "lucide-react";
import {cn, getStreamableFiles} from "@/lib/utils";
import {File} from "@/models/file.model";
import {usePrevious} from "@/hooks/usePrevious";
import {triblerService} from "@/services/tribler.service";
import {isErrorDict} from "@/services/reporting";
import {VideoJS} from "./VideoJS";
import Qt from "./Qt";
import {useFullscreen} from "@/contexts/FullScreen";

export default function VideoPlayer() {
    const navigate = useNavigate();
    const location = useLocation();
    const {infohash, file: fileString} = useParams<{infohash: string; file: string}>();
    const file = fileString ? Number(fileString) : undefined;

    const prevInfohash = usePrevious(infohash);

    const [isQt] = useState(typeof (window as any).qt !== "undefined");
    const {isFullscreen, setFullscreen} = useFullscreen();

    const [open, setOpen] = useState(false);
    const [videoFiles, setVideoFiles] = useState<File[]>([]);
    const selectedFile = videoFiles.find((f) => f.index === file);

    useEffect(() => {
        if (!infohash) {
            setVideoFiles([]);
            return;
        }

        if (prevInfohash !== infohash) {
            triblerService.getDownloadFiles(infohash).then((response) => {
                if (response !== undefined && !isErrorDict(response)) {
                    setVideoFiles(getStreamableFiles(response).sort((a, b) => (a.name > b.name ? 1 : -1)));
                } else {
                    setVideoFiles([]);
                }
            });
        }
    }, [infohash]);

    useEffect(() => {
        // If file isn't set in the URL, redirect to the first streamable file, if any.
        if (infohash && file === undefined && videoFiles.length > 0) {
            const firstFile = videoFiles[0];
            console.log("Auto-selecting first streamable file:", firstFile.name);
            navigate(`/stream/${infohash}/${firstFile.index}`, {replace: true, state: location.state});
        }
    }, [infohash, file, videoFiles, navigate]);

    console.log(infohash, file, selectedFile, infohash && file && !!selectedFile);

    return (
        <div className="w-full h-full flex flex-col overflow-hidden">
            <div className="w-full flex flex-col h-full">
                {!isFullscreen && (
                    <div className="flex items-center gap-1 w-full p-4 bg-background">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => navigate(-1)}
                            className="text-muted-foreground hover:text-foreground shrink-0"
                            title="Back">
                            <ChevronLeft className="h-8 w-8" />
                        </Button>
                        <Popover open={open} onOpenChange={setOpen}>
                            <PopoverTrigger asChild>
                                <Button
                                    variant="outline"
                                    role="combobox"
                                    aria-expanded={open}
                                    className="flex-1 justify-between">
                                    {selectedFile ? selectedFile.name : "Select video file..."}
                                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-[--radix-popover-trigger-width] p-0">
                                <Command>
                                    <CommandInput placeholder="Search video file..." />
                                    <CommandList>
                                        <CommandEmpty>No video files found.</CommandEmpty>
                                        <CommandGroup>
                                            {videoFiles.map((videoFile) => (
                                                <CommandItem
                                                    key={videoFile.index}
                                                    value={videoFile.name}
                                                    onSelect={(currentName) => {
                                                        const file = videoFiles.find(
                                                            (videoFile) => videoFile.name === currentName
                                                        );
                                                        console.log("Changed selected video file to " + file?.name);
                                                        navigate(`/stream/${infohash}/${videoFile.index}`);
                                                        setOpen(false);
                                                    }}>
                                                    <Check
                                                        className={cn(
                                                            "mr-2 h-4 w-4",
                                                            file === videoFile.index ? "opacity-100" : "opacity-0"
                                                        )}
                                                    />
                                                    {videoFile.name}
                                                </CommandItem>
                                            ))}
                                        </CommandGroup>
                                    </CommandList>
                                </Command>
                            </PopoverContent>
                        </Popover>
                    </div>
                )}

                {infohash && file !== undefined && !!selectedFile ? (
                    isQt ? (
                        <Qt infohash={infohash} file={file} />
                    ) : (
                        <VideoJS infohash={infohash} file={file} />
                    )
                ) : (
                    <div className="flex items-center justify-center h-64 bg-background text-white">
                        File is not streamable
                    </div>
                )}
            </div>
        </div>
    );
}
