import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radiogroup";
import { Settings } from "@/models/settings.model";
import { triblerService } from "@/services/tribler.service";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import SaveButton from "./SaveButton";


export default function Seeding() {
    const { t } = useTranslation();
    const [settings, setSettings] = useState<Settings>();

    if (!settings) {
        (async () => { setSettings(await triblerService.getSettings()) })();
        return;
    }

    return (
        <div className="p-6 w-full">
            <RadioGroup
                defaultValue="forever"
                onValueChange={(value) => {
                    if (settings) {
                        setSettings({
                            ...settings,
                            libtorrent: {
                                ...settings.libtorrent,
                                download_defaults: {
                                    ...settings.libtorrent.download_defaults,
                                    seeding_mode: value
                                }
                            }
                        });
                    }
                }}
            >
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value="ratio" id="seeding_ratio" />
                    <Label htmlFor="seeding_ratio">{t('SeedRatio')}</Label>
                    <Input
                        id="seeding_ratio"
                        type="number"
                        step="0.1"
                        className="w-20"
                        value={settings?.libtorrent?.download_defaults?.seeding_ratio}
                        onChange={(event) => {
                            if (settings) {
                                setSettings({
                                    ...settings,
                                    libtorrent: {
                                        ...settings.libtorrent,
                                        download_defaults: {
                                            ...settings.libtorrent.download_defaults,
                                            seeding_ratio: Math.max(0, +event.target.value)
                                        }
                                    }
                                });
                            }
                        }}
                    />
                </div>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value="forever" id="forever" />
                    <Label htmlFor="forever">{t('SeedForever')}</Label>
                </div>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value="time" id="seeding_time" />
                    <Label htmlFor="seeding_time">{t('SeedTime')}</Label>
                    <Input
                        id="seeding_time"
                        type="number"
                        className="w-20"
                        value={settings?.libtorrent?.download_defaults?.seeding_time}
                        onChange={(event) => {
                            if (settings) {
                                setSettings({
                                    ...settings,
                                    libtorrent: {
                                        ...settings.libtorrent,
                                        download_defaults: {
                                            ...settings.libtorrent.download_defaults,
                                            seeding_time: Math.max(0, +event.target.value)
                                        }
                                    }
                                });
                            }
                        }}
                    />
                </div>
                <div className="flex items-center space-x-2">
                    <RadioGroupItem value="never" id="never" />
                    <Label htmlFor="never">{t('NoSeeding')}</Label>
                </div>
            </RadioGroup>
            <p className="text-xs pt-2 pb-4 text-muted-foreground">{t('SeedingNote')}</p>

            <SaveButton
                onClick={async () => {
                    if (settings)
                        await triblerService.setSettings(settings);
                }}
            />
        </div>
    )
}
