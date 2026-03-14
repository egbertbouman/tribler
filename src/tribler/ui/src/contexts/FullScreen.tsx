import {createContext, useState, ReactNode, useMemo, useContext} from "react";

const FullscreenContext = createContext<{
    isFullscreen: boolean;
    setFullscreen: (value: boolean) => void;
}>({
    isFullscreen: false,
    setFullscreen: () => {},
});

export const FullscreenProvider = ({children}: {children: ReactNode}) => {
    const [isFullscreen, setIsFullscreen] = useState(false);

    const value = useMemo(
        () => ({
            isFullscreen,
            setFullscreen: (value: boolean) => setIsFullscreen(value),
        }),
        [isFullscreen]
    );

    return <FullscreenContext.Provider value={value}>{children}</FullscreenContext.Provider>;
};

export const useFullscreen = () => useContext(FullscreenContext);
