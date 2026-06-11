package com.example.opinion_analysis.model;

public class ChannelDTO {
    private String channel;
    private int value;

    public ChannelDTO() {}

    public ChannelDTO(String channel, int value) {
        this.channel = channel;
        this.value = value;
    }

    public String getChannel() {
        return channel;
    }

    public void setChannel(String channel) {
        this.channel = channel;
    }

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }
}
