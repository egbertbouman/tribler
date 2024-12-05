import SimpleTable, { getHeader } from "@/components/ui/simple-table";
import SaveAs from "@/dialogs/SaveAs";
import { useCallback, useEffect, useMemo, useState } from "react";
import { triblerService } from "@/services/tribler.service";
import { isErrorDict } from "@/services/reporting";
import { Torrent } from "@/models/torrent.model";
import { ColumnDef } from "@tanstack/react-table";
import { categoryIcon, filterDuplicates, formatBytes, formatTimeAgo, getMagnetLink } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useInterval } from '@/hooks/useInterval';


const getColumns = ({ onDownload }: { onDownload: (torrent: Torrent) => void }): ColumnDef<Torrent>[] => [
    {
        accessorKey: "category",
        header: "",
        cell: ({ row }) => {
            return (
                <TooltipProvider>
                    <Tooltip>
                        <TooltipTrigger><span>{categoryIcon(row.original.category)}</span></TooltipTrigger>
                        <TooltipContent>
                            {row.original.category}
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            )
        },
    },
    {
        accessorKey: "name",
        header: getHeader('Name'),
        cell: ({ row }) => {
            return <span
                className="cursor-pointer hover:underline break-all line-clamp-1"
                onClick={() => onDownload(row.original)}>
                {row.original.name}
            </span>
        },
    },
    {
        accessorKey: "size",
        header: getHeader('Size'),
        cell: ({ row }) => {
            return <span className="whitespace-nowrap">{formatBytes(row.original.size)}</span>
        },
    },
    {
        accessorKey: "created",
        header: getHeader('Created'),
        cell: ({ row }) => {
            return <span className="whitespace-nowrap">{formatTimeAgo(row.original.created)}</span>
        },
    },
]

export default function Popular() {
    const [open, setOpen] = useState<boolean>(false)
    const [torrents, setTorrents] = useState<Torrent[]>([])
    const [torrentDoubleClicked, setTorrentDoubleClicked] = useState<Torrent | undefined>();

    useInterval(async () => {
        const popular = await triblerService.getPopularTorrents();
        if (!(popular === undefined) && !isErrorDict(popular)) {
            // Don't bother the user on error, just try again later.
            setTorrents(filterDuplicates(popular, 'infohash'));
        }

        await triblerService.searchTorrentsRemote('', true);
        // We're not processing incoming results from remote search, instead additional
        // results will appear during the next run. This prevents issues with torrents
        // quickly being added and removed.
    }, 5000, true);

    const handleDownload = useCallback((torrent: Torrent) => {
        setTorrentDoubleClicked(torrent);
        setOpen(true);
    }, []);

    const torrentColumns = useMemo(() => getColumns({ onDownload: handleDownload }), [handleDownload]);

    return (
        <>
            {torrentDoubleClicked &&
                <SaveAs
                    open={open}
                    onOpenChange={() => {
                        setTorrentDoubleClicked(undefined)
                        setOpen(false);
                    }}
                    uri={getMagnetLink(torrentDoubleClicked.infohash, torrentDoubleClicked.name)}
                />
            }
            <SimpleTable
                data={torrents}
                columns={torrentColumns}
                storeSortingState="popular-sorting"
                rowId={(row) => row.infohash}
            />
        </>
    )
}
